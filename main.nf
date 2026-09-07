nextflow.enable.dsl = 2

params.samplesheet = "samplesheet.csv"
params.outdir      = "results"

process POD5_VIEW {
    tag "${meta.run_id}"
    publishDir "${params.outdir}/reads", mode: 'copy'

    input:
    tuple val(meta), path(pod5)

    output:
    tuple val(meta), path("*.reads.tsv"), emit: reads

    script:
    """
    pod5 view ${pod5} --output ${meta.run_id}.reads.tsv
    """
}

process QC_SUMMARY {
    tag "${meta.run_id}"
    publishDir "${params.outdir}/qc", mode: 'copy'

    input:
    tuple val(meta), path(tsv)

    output:
    path "*.qc.json"
    path "*.reads.parquet"

    script:
    """
    qc_summary.py \\
        --reads ${tsv} \\
        --run-id ${meta.run_id} \\
        --sample-id ${meta.sample_id} \\
        --condition ${meta.condition} \\
        --json-out ${meta.run_id}.qc.json \\
        --parquet-out ${meta.run_id}.reads.parquet
    """
}

process CLASSIFY {
    tag "${meta.run_id}"
    publishDir "${params.outdir}/classified", mode: 'copy'

    input:
    tuple val(meta), path(tsv)

    output:
    path "*.classified.parquet"

    script:
    """
    classify.py \\
        --reads ${tsv} \\
        --run-id ${meta.run_id} \\
        --out ${meta.run_id}.classified.parquet
    """
}

workflow {
    Channel
        .fromPath(params.samplesheet)
        .splitCsv(header: true)
        .map { row ->
            def meta = [
                run_id   : row.run_id,
                sample_id: row.sample_id,
                condition: row.condition,
                flowcell : row.flowcell
            ]
            tuple(meta, file(row.pod5_path))
        }
        .set { ch_input }

    POD5_VIEW(ch_input)
    QC_SUMMARY(POD5_VIEW.out.reads)
    CLASSIFY(POD5_VIEW.out.reads)
}
