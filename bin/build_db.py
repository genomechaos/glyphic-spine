#!/usr/bin/env python3
"""Create DuckDB views over the pipeline's Parquet and JSON outputs.

No data is copied. The views point at the files the pipeline wrote, so the
database can never drift out of sync with the pipeline output.
"""
import os
import duckdb

DB = "results/glyphic.duckdb"
os.makedirs("results", exist_ok=True)
con = duckdb.connect(DB)

con.execute("""
    CREATE OR REPLACE VIEW reads AS
    SELECT * FROM read_parquet('results/qc/*.reads.parquet')
""")

con.execute("""
    CREATE OR REPLACE VIEW runs AS
    SELECT * FROM read_json_auto('results/qc/*.qc.json')
""")

con.execute("""
    CREATE OR REPLACE VIEW classified AS
    SELECT * FROM read_parquet('results/classified/*.classified.parquet')
""")

for view in ("reads", "runs", "classified"):
    n = con.execute(f"SELECT count(*) FROM {view}").fetchone()[0]
    print(f"{view:12s} {n:>9,} rows")

print("\nmodel versions present:")
rows = con.execute("""
    SELECT model_name, model_version, count(*) AS n
    FROM classified
    GROUP BY 1, 2
    ORDER BY 2
""").fetchall()
for name, version, n in rows:
    print(f"  {name} v{version}: {n:,} rows")

con.close()
print(f"\nwrote {DB}")
