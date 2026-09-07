"""glyphic-spine QC dashboard.

Builds the view layer in its own in-memory DuckDB connection from
sql/views.sql, so nothing is shared, nothing is locked, and the numbers
here are by construction the same ones the CLI reports.
"""
import sys

sys.path.insert(0, "bin")

import duckdb
import streamlit as st

from views import apply_views

QSCORE_THRESHOLD = 15.0

st.set_page_config(page_title="glyphic-spine QC", layout="wide")


@st.cache_resource
def get_con():
    return apply_views(duckdb.connect())


con = get_con()

st.title("glyphic-spine — run QC")
st.caption(
    "Signal metadata, basecall outcomes and model calls for the same reads, "
    "queried in place from the pipeline's Parquet output."
)

if st.button("Refresh"):
    st.cache_resource.clear()
    st.rerun()

runs = [r[0] for r in
        con.sql("SELECT DISTINCT run_id FROM reads_full ORDER BY 1").fetchall()]
sel = st.multiselect("Runs", runs, default=runs)
if not sel:
    st.warning("Select at least one run.")
    st.stop()

where = "run_id IN (" + ",".join("'" + r.replace("'", "''") + "'" for r in sel) + ")"

# ---------------------------------------------------------------- headline
m = con.sql(f"""
    SELECT count(*)                                              AS reads,
           sum(CASE WHEN basecalled THEN 1 ELSE 0 END)           AS basecalled,
           count(DISTINCT channel)                               AS channels,
           median(n_bases)                                       AS median_bases,
           median(mean_qscore)                                   AS median_q,
           avg(CASE WHEN mean_qscore < {QSCORE_THRESHOLD}
                    THEN 1.0 ELSE 0.0 END)                       AS pct_low
    FROM reads_full WHERE {where}
""").df().iloc[0]

c1, c2, c3, c4, c5 = st.columns(5)
c1.metric("Reads", f"{int(m.reads):,}")
c2.metric("Basecalled", f"{int(m.basecalled):,}",
          f"{m.basecalled / m.reads:.1%}")
c3.metric("Active channels", f"{int(m.channels):,}")
c4.metric("Median read", f"{m.median_bases:,.0f} b"
          if m.median_bases == m.median_bases else "—")
c5.metric("Median Q", f"{m.median_q:.1f}" if m.median_q == m.median_q else "—",
          f"{m.pct_low:.1%} below Q{QSCORE_THRESHOLD:.0f}",
          delta_color="inverse")

# ---------------------------------------------------------------- yield
st.subheader("Yield")
y1, y2 = st.columns(2)

with y1:
    st.caption("Read length (bases)")
    st.bar_chart(
        con.sql(f"""
            SELECT floor(n_bases / 250) * 250 AS bases, count(*) AS reads
            FROM reads_full WHERE {where} AND basecalled
            GROUP BY 1 ORDER BY 1
        """).df().set_index("bases"))

with y2:
    st.caption("Reads per channel")
    st.bar_chart(
        con.sql(f"""
            SELECT channel, count(*) AS reads
            FROM reads_full WHERE {where}
            GROUP BY 1 ORDER BY 1
        """).df().set_index("channel"))

# ---------------------------------------------------------------- quality
st.subheader("Basecall quality")
q1, q2 = st.columns(2)

with q1:
    st.caption("Mean qscore distribution")
    st.bar_chart(
        con.sql(f"""
            SELECT round(mean_qscore) AS qscore, count(*) AS reads
            FROM reads_full WHERE {where} AND basecalled
            GROUP BY 1 ORDER BY 1
        """).df().set_index("qscore"))

with q2:
    st.caption("Median qscore by read length")
    st.line_chart(
        con.sql(f"""
            SELECT floor(n_bases / 500) * 500 AS bases,
                   median(mean_qscore)        AS median_q
            FROM reads_full WHERE {where} AND basecalled
            GROUP BY 1 HAVING count(*) > 50 ORDER BY 1
        """).df().set_index("bases"))

# ------------------------------------------------------- the actual finding
st.subheader("Does the instrument's end_reason predict data quality?")
st.caption(
    "The read-QC classifier was trained on end_reason. Basecall quality is an "
    "independent measurement of the same reads. Reads that end early are "
    "shorter — but not meaningfully worse per base."
)
st.dataframe(
    con.sql(f"""
        SELECT end_reason,
               count(*)                       AS reads,
               round(median(n_bases), 0)      AS median_bases,
               round(median(mean_qscore), 2)  AS median_qscore
        FROM reads_full WHERE {where} AND basecalled
        GROUP BY 1 ORDER BY reads DESC
    """).df(), use_container_width=True, hide_index=True)

# ---------------------------------------------------------------- provenance
st.subheader("Model provenance")
st.caption(
    "Every prediction carries the registry version that produced it. "
    "Retraining bumps the version; historical rows keep theirs."
)
st.dataframe(
    con.sql(f"""
        SELECT model_version,
               pred_normal,
               count(*)                       AS reads,
               round(median(mean_qscore), 2)  AS median_qscore
        FROM reads_full WHERE {where} AND model_version IS NOT NULL
        GROUP BY 1, 2 ORDER BY 1, 2
    """).df(), use_container_width=True, hide_index=True)
