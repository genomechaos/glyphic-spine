CREATE OR REPLACE VIEW reads AS
SELECT * FROM read_parquet('results/qc/*.reads.parquet')
;
CREATE OR REPLACE VIEW runs AS
SELECT * FROM read_json_auto('results/qc/*.qc.json')
;
CREATE OR REPLACE VIEW classified AS
SELECT * FROM read_parquet('results/classified/*.classified.parquet')
;
CREATE OR REPLACE VIEW basecalls AS
SELECT * FROM read_parquet('results/basecalled/*.basecalls.parquet')
;
CREATE OR REPLACE VIEW basecall_by_read AS
SELECT
    parent_read_id                                AS read_id,
    count(*)                                      AS n_subreads,
    bool_or(is_split)                             AS is_split,
    sum(n_bases)                                  AS n_bases,
    sum(mean_qscore * n_bases)
        / nullif(sum(n_bases), 0)                 AS mean_qscore
FROM basecalls
GROUP BY parent_read_id
;
CREATE OR REPLACE VIEW reads_full AS
SELECT
    r.*,
    c.p_normal,
    c.pred_normal,
    c.model_version,
    b.n_bases,
    b.mean_qscore,
    b.n_subreads,
    coalesce(b.is_split, FALSE) AS is_split,
    (b.n_subreads IS NOT NULL)  AS basecalled
FROM reads r
LEFT JOIN classified c       USING (read_id)
LEFT JOIN basecall_by_read b USING (read_id)
