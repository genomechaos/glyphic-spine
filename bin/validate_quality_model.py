#!/usr/bin/env python3
"""Does the quality model generalise, or has it memorised the flow cell?

`channel` carries ~22% of the model's importance. Under a random read-level
split, the model can learn "channel 173 is bad" and be graded on held-out reads
from channel 173 — which says nothing about a new flow cell. This compares:

  1. random split, all features        (optimistic; what we reported)
  2. grouped split by channel          (can it generalise to unseen pores?)
  3. grouped split, channel dropped    (how much was the channel identity worth?)
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import duckdb
import mlflow
import pandas as pd
from sklearn.ensemble import RandomForestClassifier
from sklearn.metrics import (accuracy_score, average_precision_score,
                             precision_score, recall_score, roc_auc_score)
from sklearn.model_selection import GroupShuffleSplit, train_test_split

from views import apply_views

THRESHOLD = 15.0


def evaluate(X, y, tr, te, label):
    clf = RandomForestClassifier(
        n_estimators=300, class_weight="balanced",
        min_samples_leaf=5, n_jobs=-1, random_state=0)
    clf.fit(X.iloc[tr], y.iloc[tr])

    proba = clf.predict_proba(X.iloc[te])[:, 1]
    pred = clf.predict(X.iloc[te])
    yte = y.iloc[te]

    return {
        "split": label,
        "n_test": len(te),
        "pos_rate": round(float(yte.mean()), 4),
        "accuracy": round(accuracy_score(yte, pred), 4),
        "roc_auc": round(roc_auc_score(yte, proba), 4),
        "pr_auc": round(average_precision_score(yte, proba), 4),
        "lift": round(average_precision_score(yte, proba) / yte.mean(), 2),
        "precision": round(precision_score(yte, pred, zero_division=0), 4),
        "recall": round(recall_score(yte, pred, zero_division=0), 4),
    }


def main():
    con = apply_views(duckdb.connect())
    df = con.sql("SELECT * FROM reads_full WHERE basecalled").df()

    lencol = next((c for c in ("num_samples", "sample_count")
                   if c in df.columns), None)
    feats = [c for c in (lencol, "median_before", "channel", "start_sample")
             if c and c in df.columns]

    X = df[feats].copy()
    X["is_signal_positive"] = (df["end_reason"] == "signal_positive").astype(int)
    X = X.fillna(X.median(numeric_only=True))
    y = (df["mean_qscore"] < THRESHOLD).astype(int)
    groups = df["channel"]

    print(f"{len(df):,} reads, {groups.nunique()} channels, "
          f"{y.mean():.2%} positive\n")

    results = []

    tr, te = train_test_split(range(len(X)), test_size=0.25,
                              random_state=0, stratify=y)
    results.append(evaluate(X, y, list(tr), list(te), "random reads"))

    gss = GroupShuffleSplit(n_splits=1, test_size=0.25, random_state=0)
    gtr, gte = next(gss.split(X, y, groups=groups))
    results.append(evaluate(X, y, list(gtr), list(gte), "held-out channels"))

    Xnc = X.drop(columns=["channel"])
    results.append(evaluate(Xnc, y, list(gtr), list(gte),
                            "held-out channels, no channel feature"))

    out = pd.DataFrame(results)
    print(out.to_string(index=False))

    mlflow.set_tracking_uri(os.environ.get("MLFLOW_TRACKING_URI",
                                           "sqlite:///mlruns.db"))
    mlflow.set_experiment("read-quality-validation")
    for r in results:
        with mlflow.start_run(run_name=r["split"]):
            mlflow.log_param("split", r["split"])
            mlflow.log_param("qscore_threshold", THRESHOLD)
            mlflow.log_metrics({k: v for k, v in r.items()
                                if k != "split"})

    print("\nlogged 3 runs to experiment 'read-quality-validation'")


if __name__ == "__main__":
    main()
