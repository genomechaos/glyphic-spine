#!/usr/bin/env python3
"""Train a read-QC classifier and log it to the MLflow registry."""
import duckdb
import mlflow
import mlflow.sklearn
from sklearn.ensemble import RandomForestClassifier
from sklearn.metrics import (accuracy_score, average_precision_score,
                             precision_score, recall_score, roc_auc_score)
from sklearn.model_selection import train_test_split

mlflow.set_tracking_uri("sqlite:///mlruns.db")
mlflow.set_experiment("read-qc")

con = duckdb.connect("results/glyphic.duckdb", read_only=True)
df = con.execute("SELECT * FROM reads WHERE end_reason IS NOT NULL").fetchdf()
con.close()

lencol = next(c for c in ("num_samples", "sample_count") if c in df.columns)
features = [c for c in (lencol, "median_before", "channel", "start_sample")
            if c in df.columns]

X = df[features].fillna(0)
y = (df["end_reason"] == "signal_positive").astype(int)

X_tr, X_te, y_tr, y_te = train_test_split(
    X, y, test_size=0.25, random_state=0, stratify=y
)

params = {"n_estimators": 200, "max_depth": 8, "random_state": 0,
          "class_weight": "balanced"}

with mlflow.start_run() as run:
    clf = RandomForestClassifier(**params).fit(X_tr, y_tr)
    pred = clf.predict(X_te)
    proba = clf.predict_proba(X_te)[:, 1]

    y_rare, pred_rare, score_rare = 1 - y_te, 1 - pred, 1 - proba
    baseline = max(y_te.mean(), 1 - y_te.mean())

    mlflow.log_params(params)
    mlflow.log_param("features", ",".join(features))
    mlflow.log_param("label", "end_reason == signal_positive")
    mlflow.log_metric("n_train", len(X_tr))
    mlflow.log_metric("baseline_accuracy", baseline)
    mlflow.log_metric("pr_auc_random", 1 - baseline)
    mlflow.log_metric("accuracy", accuracy_score(y_te, pred))
    mlflow.log_metric("roc_auc", roc_auc_score(y_te, proba))
    mlflow.log_metric("pr_auc_rare", average_precision_score(y_rare, score_rare))
    mlflow.log_metric("precision_rare", precision_score(y_rare, pred_rare, zero_division=0))
    mlflow.log_metric("recall_rare", recall_score(y_rare, pred_rare, zero_division=0))

    try:
        mlflow.sklearn.log_model(clf, name="model", registered_model_name="read-qc")
    except TypeError:
        mlflow.sklearn.log_model(clf, artifact_path="model", registered_model_name="read-qc")

    print("baseline:", round(baseline, 4))
    print("accuracy:", round(accuracy_score(y_te, pred), 4))
    print("roc_auc :", round(roc_auc_score(y_te, proba), 4))
    print("PR-AUC (rare):", round(average_precision_score(y_rare, score_rare), 4))
    print("precision/recall (rare):",
          round(precision_score(y_rare, pred_rare, zero_division=0), 4),
          round(recall_score(y_rare, pred_rare, zero_division=0), 4))
