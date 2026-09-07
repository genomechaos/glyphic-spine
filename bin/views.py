"""Single source of truth for the DuckDB view layer.

The views are SQL over Parquet the pipeline already wrote, so they cost nothing
to rebuild. Callers use their own in-memory connection rather than sharing a
database file, which means no lock contention between the dashboard and the CLI.
"""
import os

SQL_PATH = os.path.join(os.path.dirname(os.path.dirname(
    os.path.abspath(__file__))), "sql", "views.sql")


def apply_views(con, sql_path=SQL_PATH):
    with open(sql_path) as fh:
        body = fh.read()
    for stmt in (s.strip() for s in body.split(";")):
        if stmt:
            con.execute(stmt)
    return con
