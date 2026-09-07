#!/usr/bin/env python3
"""Predict poor basecall quality from pre-basecall signal features.

The earlier read-QC model was trained on `end_reason`, which turned out to
predict read length rather than data quality. This one targets the outcome
directly: will this read basecall below a quality threshold? Every feature is
available before basecalling, so the model could in principle run at the
instrument.
"""
import argparse
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import duckdb
import mlflow
import mlflow.sklearn
import pandas as pd
from sklearn.ensemble import RandomForestClassifier
from sklearn.metrics import (accuracy_score, average_precision_score,
                             precision_score, recall_score, roc_auc_score)
from sklearn.model_selection import train_test_split

from views import apply_views


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--qscore-threshold", type=float, default=15.0)
    ap.add_argument("--tracking-uri",
                    default=os.environ.get("MLFLOW_TRACKING_URI",
                                           "sqlite:///mlruns.db"))
    args = ap.parse_args()

    con = apply_views(duckdb.connect())
    df = con.sql("SELECT * FROM reads_full WHERE basecalled").df()
    print(f"{len(df):,} basecalled reads")

    lencol = next((c for c in ("num_samples", "sample_count")
                   if c in df.columns), None)
    feats = [c for c in (lencol, "median_before", "channel", "start_sample")
             if c and c in df.columns]

    X = df[feats].copy()
    X["is_signal_positive"] = (df["end_reason"] == "signal_positive").astype(int)
    X = X.fillna(X.median(numeric_only=True))

    y = (df["mean_qscore"] < args.qscore_threshold).astype(int)
    rate = y.mean()
    print(f"features: {list(X.columns)}")
    print(f"label: mean_qscore < {args.qscore_threshold}  "
          f"-> {y.sum():,} positives ({rate:.2%})")

    if y.sum() < 50:
        print("\nToo few positives to train on. Raise --qscore-threshold.")
        return

    Xtr, Xte, ytr, yte = train_test_split(
        X, y, test_size=0.25, random_state=0, stratify=y)

    clf = RandomForestClassifier(
        n_estimators=300, class_weight="balanced",
        min_samples_leaf=5, n_jobs=-1, random_state=0)
    clf.fit(Xtr, ytr)

    proba = clf.predict_proba(Xte)[:, 1]
    pred = clf.predict(Xte)

    baseline = max(1 - yte.mean(), yte.mean())
    metrics = {
        "baseline_accuracy": baseline,
        "accuracy":          accuracy_score(yte, pred),
        "roc_auc":           roc_auc_score(yte, proba),
        "pr_auc":            average_precision_score(yte, proba),
        "pr_auc_random":     yte.mean(),
        "precision":         precision_score(yte, pred, zero_division=0),
        "recall":            recall_score(yte, pred, zero_division=0),
    }

    mlflow.set_tracking_uri(args.tracking_uri)
    mlflow.set_experiment("read-quality")
    with mlflow.start_run():
        mlflow.log_params({
            "qscore_threshold": args.qscore_threshold,
            "features": ",".join(X.columns),
            "n_train": len(Xtr),
            "n_test": len(Xte),
            "positive_rate": round(float(rate), 4),
        })
        mlflow.log_metrics(metrics)
        try:
            mlflow.sklearn.log_model(clf, name="model",
                                     registered_model_name="read-quality")
        except TypeError:
            mlflow.sklearn.log_model(clf, artifact_path="model",
                                     registered_model_name="read-quality")

    print("\n=== metrics ===")
    for k, v in metrics.items():
        print(f"{k:20s} {v:.4f}")

    lift = metrics["pr_auc"] / metrics["pr_auc_random"]
    print(f"\nPR-AUC lift over random: {lift:.1f}x")

    print("\n=== feature importance ===")
    imp = pd.Series(clf.feature_importances_, index=X.columns)
    for name, val in imp.sort_values(ascending=False).items():
        print(f"{name:20s} {val:.4f}")


if __name__ == "__main__":
    main()
