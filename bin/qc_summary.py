#!/usr/bin/env python3
import argparse, json
import pandas as pd

def main():
    p = argparse.ArgumentParser()
    p.add_argument("--reads",       required=True)
    p.add_argument("--run-id",      required=True)
    p.add_argument("--sample-id",   required=True)
    p.add_argument("--condition",   required=True)
    p.add_argument("--json-out",    required=True)
    p.add_argument("--parquet-out", required=True)
    a = p.parse_args()

    df = pd.read_csv(a.reads, sep="\t")
    df["run_id"]    = a.run_id
    df["sample_id"] = a.sample_id
    df["condition"] = a.condition
    df.to_parquet(a.parquet_out, index=False)

    m = {
        "run_id":    a.run_id,
        "sample_id": a.sample_id,
        "condition": a.condition,
        "read_count": int(len(df)),
    }

    lencol = next((c for c in ("num_samples", "sample_count") if c in df.columns), None)
    if lencol:
        m["total_samples"] = int(df[lencol].sum())
        m["read_length"] = {
            "p10":    int(df[lencol].quantile(0.10)),
            "median": int(df[lencol].median()),
            "p90":    int(df[lencol].quantile(0.90)),
        }

    if "end_reason" in df.columns:
        m["end_reason"] = df["end_reason"].value_counts().to_dict()

    if "channel" in df.columns:
        ch = df.groupby("channel").size()
        m["channels"] = {
            "n_active":  int(ch.size),
            "reads_min": int(ch.min()),
            "reads_max": int(ch.max()),
        }

    with open(a.json_out, "w") as f:
        json.dump(m, f, indent=2)
    print(json.dumps(m, indent=2))

if __name__ == "__main__":
    main()
