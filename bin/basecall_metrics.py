#!/usr/bin/env python3
"""Per-read basecall metrics from an unaligned Dorado BAM.

Dorado splits reads that contain more than one molecule. Each split gets a new
read_id and carries its POD5 read_id in the 'pi' tag. Joining on read_id alone
silently drops every split read, so we key on parent_read_id instead.
"""
import argparse
import pandas as pd
import pysam


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--bam", required=True)
    ap.add_argument("--run-id", required=True)
    ap.add_argument("--out", required=True)
    args = ap.parse_args()

    rows = []
    with pysam.AlignmentFile(args.bam, "rb", check_sq=False) as bam:
        for rec in bam:
            tags = dict(rec.tags)
            seq = rec.query_sequence or ""
            parent = tags.get("pi") or rec.query_name
            rows.append({
                "read_id":        rec.query_name,
                "parent_read_id": parent,
                "is_split":       parent != rec.query_name,
                "n_bases":        len(seq),
                "mean_qscore":    tags.get("qs"),
                "n_samples_bam":  tags.get("ns"),
                "trim_samples":   tags.get("ts"),
                "run_id":         args.run_id,
            })

    df = pd.DataFrame(rows)
    df.to_parquet(args.out, index=False)

    n_split = int(df["is_split"].sum())
    print(f"{len(df):,} records written to {args.out}")
    print(f"{n_split:,} are split sub-reads from "
          f"{df.loc[df['is_split'], 'parent_read_id'].nunique():,} parent reads\n")
    print(df[["n_bases", "mean_qscore"]].describe().to_string())

    if df["n_samples_bam"].notna().any():
        ratio = (df["n_samples_bam"] / df["n_bases"]).replace(
            [float("inf"), float("-inf")], pd.NA).dropna()
        print(f"\nmedian samples per base: {ratio.median():.2f}")


if __name__ == "__main__":
    main()
