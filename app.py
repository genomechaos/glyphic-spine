#!/usr/bin/env python3
import duckdb
import pandas as pd
import streamlit as st

st.set_page_config(page_title="glyphic-spine QC", layout="wide")

@st.cache_resource
def get_con():
    return duckdb.connect("results/glyphic.duckdb", read_only=True)

con = get_con()
runs = con.execute("SELECT * FROM runs").fetchdf()

st.title("Nanopore run QC")

selected = st.sidebar.multiselect(
    "Runs",
    options=sorted(runs["run_id"]),
    default=sorted(runs["run_id"]),
)
if not selected:
    st.warning("Select at least one run.")
    st.stop()

placeholders = ",".join("?" * len(selected))
reads = con.execute(
    f"SELECT * FROM reads WHERE run_id IN ({placeholders})", selected
).fetchdf()

lencol = next((c for c in ("num_samples", "sample_count") if c in reads.columns), None)

c1, c2, c3, c4 = st.columns(4)
c1.metric("Runs", len(selected))
c2.metric("Reads", f"{len(reads):,}")
if lencol:
    c3.metric("Total samples", f"{int(reads[lencol].sum()):,}")
if "channel" in reads.columns:
    c4.metric("Active channels", reads["channel"].nunique())

st.subheader("Per-run summary")
st.dataframe(runs[runs["run_id"].isin(selected)], use_container_width=True)

if lencol:
    st.subheader("Read length distribution (samples)")
    binned = pd.cut(reads[lencol], bins=50).value_counts().sort_index()
    st.bar_chart(pd.DataFrame(
        {"reads": binned.values},
        index=[int(i.left) for i in binned.index],
    ))

if "channel" in reads.columns:
    st.subheader("Reads per channel")
    st.bar_chart(reads.groupby("channel").size().rename("reads"))

if "end_reason" in reads.columns:
    st.subheader("End reason")
    st.bar_chart(reads["end_reason"].value_counts())
