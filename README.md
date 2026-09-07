
---

## Design notes

**Metadata rides with the data.** A typed samplesheet enters the pipeline and the
run/sample/condition travel as a meta map through the whole DAG — nothing downstream
parses a filename to know what it's looking at. The run-ID convention
(`RUN<YYYYMMDD><letter>`) is enforced at pipeline entry, not by habit.

**No ETL.** The Parquet files the pipeline writes *are* the storage layer; DuckDB
queries them in place through views. Nothing is copied, so nothing can drift out of
sync with what the pipeline actually produced. Adding a run to the database means
running the pipeline.

**Provenance is a byproduct.** `bin/train_model.py` registers the classifier in MLflow;
`bin/classify.py` loads the latest registered version and writes `model_name`,
`model_version`, `model_run_id` and `classified_at` onto every row. Retraining bumps
the version and historical rows keep theirs, so if a run's calls look wrong later you
can tell whether the model changed underneath them.

---

## The model

A read-QC classifier: predicts whether a read finished normally (`signal_positive`)
or was cut short, from read length, open-pore current, channel and start position.
Labels come straight from the instrument's own `end_reason` field — no synthetic data.

The model is not the interesting part. The registry and the version stamping are.

---

## Dashboard

![QC dashboard](docs/dashboard.png)

---

## What the data showed

**Per-channel yield is very uneven.** Average ~131 reads per channel across 500 active
channels, but the observed range was 1 to 173 — at least one pore produced effectively
nothing for the whole run. That's the argument for surfacing per-channel and
plate-level comparison in a dashboard rather than leaving it to ad-hoc scripts.

**Read length is reported in samples, not bases.** A median of 33,152 samples is roughly
2.6–3.3 kb depending on sampling rate. `sample_rate` lives in the POD5 run metadata and
is *not* in the per-read table, so it needs capturing in the schema for anything
downstream to convert without guessing.

**Accuracy was the wrong metric.** 96.6% of reads end normally, so a model predicting
"fine" for everything scores 96.6%. The first classifier scored 97.4% and looked good.
Adding `class_weight="balanced"` dropped accuracy to 86% while ROC-AUC held at 0.89 —
the model didn't get worse, the operating point moved. PR-AUC on the rare class is 0.44
against a 0.034 random baseline, about 13x lift. At 0.16 precision / 0.71 recall this is
a screening filter, not an auto-reject rule. The registry logs the baselines alongside
the metrics so the comparison is visible rather than implied.

---

## Status

Runs end to end on a local executor.

**Next:** Dorado basecalling and alignment.

**Not a production system.** No instrument integration, no alerting, no retention
policy, and it has only been run against a single flow cell of open data.
