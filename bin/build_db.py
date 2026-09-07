#!/usr/bin/env python3
"""Report on the view layer. Nothing is materialised and nothing is written.

Kept as a CLI sanity check: if this prints sensible row counts, the dashboard
will see the same numbers, because both build the views from sql/views.sql.
"""
import sys, os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import duckdb
from views import apply_views

con = apply_views(duckdb.connect())

for view in ("reads", "runs", "classified", "basecalls",
             "basecall_by_read", "reads_full"):
    n = con.execute(f"SELECT count(*) FROM {view}").fetchone()[0]
    print(f"{view:18s} {n:>9,} rows")
