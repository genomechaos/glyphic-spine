# glyphic-spine

Nextflow pipeline: nanopore POD5 signal metadata -> QC metrics -> Parquet.

## What it does
1. `POD5_VIEW`   — extracts per-read metadata from POD5 with `pod5 view`
2. `QC_SUMMARY`  — attaches sample metadata, writes per-read Parquet and run-level QC JSON

## Run
nextflow run . -profile local

## Run ID convention
`RUN<YYYYMMDD><letter>` — e.g. RUN20260901A.
Enforced at pipeline entry via `samplesheet.csv`, not by convention.

## Samplesheet
`run_id, sample_id, condition, flowcell, pod5_path`

## Notes from the first run
Test data: ONT open dataset, 65,308 reads across 500 active channels.

- **Per-channel yield is very uneven.** Average ~131 reads per channel, but the
  observed range was 1 to 173. At least one pore effectively produced nothing for
  the whole run. This is the argument for surfacing per-channel and plate-level
  comparison in a dashboard rather than leaving it to ad-hoc scripts.
- **Read length is reported in samples, not bases.** Median 33,152 samples is
  roughly 2.6–3.3 kb depending on sampling rate. `sample_rate` lives in POD5 run
  metadata and is not in the per-read table, so it needs capturing in the schema
  for anything downstream to convert without guessing.

## Status
Phase 0 — spine only. No basecalling yet.
Next: DuckDB over the Parquet, Streamlit dashboard, then Dorado.

## Dashboard

![QC dashboard](docs/dashboard.png)

Streamlit over DuckDB, which queries the pipeline's Parquet output in place —
no ETL, so the dashboard can't drift out of sync with what the pipeline produced.

Run: `streamlit run app.py`
