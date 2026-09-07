#!/usr/bin/env python3
"""Score reads with the registered model, stamping model identity on every row."""
import argparse
import os
from datetime import datetime, timezone

import mlflow
import mlflow.sklearn
import pandas as pd
from mlflow.tracking import MlflowClient

MODEL_NAME = "read-qc"


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--reads", required=True)
    p.add_argument("--run-id", required=True)
    p.add_argument("--out", required=True)
    p.add_argument("--tracking-uri",
                   default=os.environ.get("MLFLOW_TRACKING_URI", "sqlite:///mlruns.db"))
    a = p.parse_args()

    mlflow.set_tracking_uri(a.tracking_uri)
    client = MlflowClient()

    versions = client.search_model_versions(f"name='{MODEL_NAME}'")
    latest = max(versions, key=lambda v: int(v.version))
    model = mlflow.sklearn.load_model(f"models:/{MODEL_NAME}/{latest.version}")

    df = pd.read_csv(a.reads, sep="\t")
    lencol = next(c for c in ("num_samples", "sample_count") if c in df.columns)
    features = [c for c in (lencol, "median_before", "channel", "start_sample")
                if c in df.columns]

    X = df[features].fillna(0)
    df["p_normal"] = model.predict_proba(X)[:, 1]
    df["pred_normal"] = model.predict(X)

    df["run_id"] = a.run_id
    df["model_name"] = MODEL_NAME
    df["model_version"] = int(latest.version)
    df["model_run_id"] = latest.run_id
    df["classified_at"] = datetime.now(timezone.utc).isoformat()

    df.to_parquet(a.out, index=False)
    print(f"{len(df)} rows -> {a.out}")
    print(f"model {MODEL_NAME} v{latest.version}  (mlflow run {latest.run_id[:8]})")


if __name__ == "__main__":
    main()
