# glyphic-spine

A nanopore data pipeline: raw signal in, queryable QC out, with every
model-produced call traceable to the model version that produced it.

Built and tested on public data from the Oxford Nanopore open dataset.

---

## What it does

| Stage | Does |
|---|---|
| `POD5_VIEW` | Extracts per-read signal metadata from POD5 with `pod5 view` |
| `QC_SUMMARY` | Attaches sample metadata, writes per-read Parquet and run-level QC JSON |
| `CLASSIFY` | Scores every read with the registered model and stamps the model version onto each row |
| `BASECALL` | Calls signal to sequence with Dorado on GPU |
| `BASECALL_METRICS` | Per-read length and quality from the BAM, keyed to join back to the signal table |

DuckDB views query the Parquet in place; a Streamlit dashboard reads from those.

```
samplesheet.csv
      │
  [Nextflow DSL2]
      ├─ POD5_VIEW ─┬─ QC_SUMMARY       → Parquet + run QC (JSON)
      │             └─ CLASSIFY         → predictions + model provenance
      └─ BASECALL ──── BASECALL_METRICS → per-read bases + qscore
      │
  [DuckDB]  views over the Parquet, queried in place, no shared file
      │
  [Streamlit]  yield, read length, per-channel, basecall quality, provenance
```

Nextflow writes an execution report, timeline and trace to `results/_reports/`
on every run.

---

## Setup

Requires Python 3.10+, Java 17+ (for Nextflow), and a POSIX environment.
Basecalling wants an NVIDIA GPU; everything else runs on CPU.

```bash
curl -s https://get.nextflow.io | bash && sudo mv nextflow /usr/local/bin/

python3 -m venv ~/.venvs/ont && source ~/.venvs/ont/bin/activate
pip install pod5 pandas pyarrow duckdb streamlit mlflow scikit-learn pysam awscli
```

Dorado is a static binary from ONT. Extract it and point `params.dorado` in
`nextflow.config` at the executable — Nextflow tasks run in a non-interactive
shell that does not read your profile, so a `PATH` entry is not enough.

Get a POD5 file (no credentials needed):

```bash
aws s3 ls --no-sign-request s3://ont-open-data/
aws s3 cp --no-sign-request s3://ont-open-data/<path>/<file>.pod5 data/
```

Then point `samplesheet.csv` at it.

---

## Run

```bash
# one-time: register a model so CLASSIFY has something to load
python3 bin/train_model.py

nextflow run . -profile local              # pipeline, incl. GPU basecalling
python3 bin/build_db.py                    # row counts across the view layer
streamlit run app.py                       # dashboard
```

The quality model is trained after basecalls exist, since its labels come from
them:

```bash
python3 bin/train_quality_model.py         # train + register read-quality
python3 bin/validate_quality_model.py      # leakage check: held-out channels
```

MLflow tracking is a SQLite backend (`mlruns.db`). The file store does not
support the model registry, which is the whole point of using it here.

---

## Layout

```
main.nf                     Nextflow workflow — five processes
nextflow.config             executor, dorado path, MLflow tracking URI, reporting
samplesheet.csv             typed input: run_id, sample_id, condition, flowcell, pod5_path
sql/views.sql               the view layer — single source of truth
app.py                      Streamlit dashboard
bin/
  qc_summary.py             per-read Parquet + run-level QC metrics
  basecall_metrics.py       per-read bases and qscore from the Dorado BAM
  train_model.py            read-QC classifier (end_reason target)
  train_quality_model.py    basecall-quality classifier (qscore target)
  validate_quality_model.py grouped-split validation
  classify.py               loads the registered version, writes predictions + provenance
  views.py                  applies sql/views.sql to a connection
  build_db.py               row counts across the view layer
results/                    pipeline outputs (gitignored)
docs/                       screenshots
```

---

## Design notes

**Metadata rides with the data.** A typed samplesheet enters the pipeline and
run/sample/condition travel as a meta map through the whole DAG — nothing
downstream parses a filename to know what it is looking at. The run-ID
convention (`RUN<YYYYMMDD><letter>`) is enforced at pipeline entry, not by habit.

**No ETL.** The Parquet the pipeline writes *is* the storage layer; DuckDB
queries it in place through views. Nothing is copied, so nothing can drift out
of sync with what the pipeline produced. Adding a run means running the pipeline.

**No shared database file.** The views are cheap SQL over Parquet, so every
caller builds them in its own in-memory connection from `sql/views.sql`. An
earlier version kept a `.duckdb` file that existed only to hold view definitions
and deadlocked the dashboard against the CLI. Removing it removed the failure
mode rather than working around it.

**Provenance is a byproduct.** `classify.py` loads the latest registered model
and writes `model_name`, `model_version`, `model_run_id` and `classified_at`
onto every row. Retraining bumps the version and historical rows keep theirs, so
if a run's calls look wrong later you can tell whether the model changed
underneath them.

**Joins are reconciled, not assumed.** Every cross-source join in the view layer
is checked by counting rows on both sides and on the result. That habit is what
caught the read-splitting bug below, which produced no error of any kind.

---

## The models

Two, and the second exists because the first was measuring the wrong thing.

**`read-qc`** predicts whether a read ended normally, from read length,
open-pore current, channel and start position. Labels come from the
instrument's `end_reason` field. This is the model `CLASSIFY` currently loads.

**`read-quality`** predicts whether a read will basecall below Q15, from the
same pre-basecall signal features. Labels come from the basecaller. Every
feature is available before basecalling, so in principle it could run at the
instrument — early termination of a failing run, or adaptive sampling.

Neither model is the interesting part. The registry, the version stamping and
the validation are.

---

## Dashboard

![QC dashboard](docs/dashboard.png)

---

## What the data showed

One flow cell, 65,308 reads, 500 active channels.

**Per-channel yield is very uneven.** ~131 reads per channel on average, with an
observed range of 1 to 173 — at least one pore produced effectively nothing all
run. That is the argument for surfacing per-channel comparison in a dashboard
rather than in ad-hoc scripts.

**Read length is reported in samples, not bases — 13.71 samples per base.**
`sample_rate` lives in POD5 run metadata and not in the per-read table, so
anything downstream needs it captured in the schema to convert without guessing.
An earlier version of this README estimated the conversion from nominal
translocation rate and put a median read at 2.6–3.3 kb. Measured against real
basecalls it is about 2.4 kb. The estimate was replaced with the measurement.

**Accuracy was the wrong metric.** 96.6% of reads end normally, so a model
predicting "fine" for everything scores 96.6%. The first classifier scored 97.4%
and looked good. Adding `class_weight="balanced"` dropped accuracy to 86% while
ROC-AUC held at 0.89 — the model did not get worse, the operating point moved.
PR-AUC on the rare class was 0.44 against a 0.034 random baseline. The registry
logs the baseline alongside the metric so the comparison is visible rather than
implied.

**Dorado splits reads, and a naive join silently loses 3.5% of them.** Reads
containing more than one molecule are split into sub-reads with *new* UUIDs; the
POD5 read ID moves to the `pi` BAM tag. 65,308 POD5 reads produced 66,355 BAM
records — 2,296 sub-reads from 1,173 parents. Joining on `read_id` matched only
64,059 of them. Nothing errored, nothing warned, and every downstream number
would have been quietly wrong. It was caught by reconciling row counts on both
sides before trusting the join; the fix is to key on parent read ID.

**`end_reason` does not predict data quality.** With basecalls joined to signal
metadata, reads that ended early turn out to be *shorter* but not meaningfully
worse:

| `end_reason` | reads | median bases | median Q |
|---|---:|---:|---:|
| `signal_positive` | 63,073 | 2,530 | 20.40 |
| `unblock_mux_change` | 2,207 | 1,646 | 19.72 |
| `signal_negative` | 28 | 2,569 | 14.97 |

So the first classifier was predicting read length — which was also one of its
own features. The model worked; the label did not matter. Retargeting on
measured quality gives 4.0x PR-AUC lift over random, and `end_reason`
contributes 2% of that model's feature importance.

**Feature importance on a leaky split inverted the truth.** `channel` ranked
second at 22% importance. But splitting randomly by read lets the model learn
"this pore is bad" and then be graded on held-out reads from that same pore —
which says nothing about a new flow cell.

| split | PR-AUC | random | lift | precision | recall |
|---|---:|---:|---:|---:|---:|
| random reads | 0.636 | 0.161 | 3.96x | 0.564 | 0.737 |
| held-out channels | 0.552 | 0.187 | 2.95x | 0.534 | 0.560 |
| held-out channels, no `channel` feature | 0.543 | 0.187 | 2.90x | 0.497 | 0.611 |

A quarter of the apparent performance was memorisation. Dropping `channel`
entirely costs almost nothing once the split is honest — the apparent
second-most-important feature is worth under 2% for generalisation. What
survives is signal physics: read length, open-pore current, and position in the
run. Lift is the right comparison here because the grouped test set has a higher
base rate (18.7% vs 16.1%), whole bad channels having landed in it.

---

## Status

Runs end to end on a local executor. GPU basecalling of the full run takes 2m34s
on an RTX 5060 (17.0 Msamples/s, `hac` model); the whole pipeline takes 2m41s.

`hac` rather than `sup` is deliberate: roughly 5x the compute for a fraction of
a percent of accuracy is the wrong trade on a laptop GPU.

**Known gap.** `CLASSIFY` still loads `read-qc`, the model whose label this
repo's own analysis shows does not predict data quality. Pointing it at
`read-quality` means restructuring the DAG so classification runs after
basecalling, which changes the pipeline from two independent branches into a
join.

**Not a production system.** No instrument integration, no alerting, no
retention policy, no cloud executor, and it has been run against a single flow
cell of open data.
