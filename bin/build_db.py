#!/usr/bin/env python3
"""Build a DuckDB database over the pipeline's Parquet and JSON outputs."""
import duckdb

con = duckdb.connect("results/glyphic.duckdb")

con.execute("""
    CREATE OR REPLACE VIEW reads AS
    SELECT * FROM read_parquet('results/qc/*.reads.parquet')
""")

con.execute("""
    CREATE OR REPLACE VIEW runs AS
    SELECT * FROM read_json_auto('results/qc/*.qc.json')
""")

print("reads:", con.execute("SELECT count(*) FROM reads").fetchone()[0])
print(con.execute("SELECT run_id, sample_id, read_count FROM runs").fetchdf())
con.close()
