"""
Find CGP overlaps, looking only at transcripts which are tagged as best
"""
import argparse
import sys
import os
from collections import defaultdict
os.environ['PYTHONPATH'] = './:./submodules:./submodules/pycbio:./submodules/comparativeAnnotator'
sys.path.extend(['./', './submodules', './submodules/pycbio', './submodules/comparativeAnnotator'])
from pycbio.bio.transcripts import get_transcript_dict
from pycbio.bio.intervals import ChromosomeInterval
from pycbio.sys.fileOps import TemporaryFilePath
from pycbio.sys.procOps import callProcLines
from comparativeAnnotator.database_queries import get_aln_ids, get_transcript_gene_map
from comparativeAnnotator.comp_lib.name_conversions import strip_alignment_numbers


def parse_args():
    parser = argparse.ArgumentParser()
    parser.add_argument('comp_db')
    parser.add_argument('ref_genome')
    parser.add_argument('genome')
    parser.add_argument('cgp')
    parser.add_argument('transmap')
    parser.add_argument('--min_jaccard', help='Minimum jaccard score to count', default=0.4, type=float)
    res = parser.add_mutually_exclusive_group()
    res.add_argument('--remove-multiple', action='store_true')
    res.add_argument('--resolve-multiple', action='store_true')
    return parser.parse_args()


def create_chrom_dict(tx_dict):
    """
    For all transcripts on a chromosome, create a BED record of it
    """
    chrom_dict = defaultdict(dict)
    for tx_id, tx in tx_dict.iteritems():
        chrom_dict[tx.chromosome][tx_id] = [tx, '\t'.join(map(str, tx.get_bed())) + '\n']
    return chrom_dict


def filter_tm_txs(cgp_tx, tm_tx_dict):
    """reduce transcripts to those who intersect the cgp_tx"""
    cgp_interval = ChromosomeInterval(cgp_tx.chromosome, cgp_tx.start, cgp_tx.stop, cgp_tx.strand)
    r = []
    for tx, bed_rec in tm_tx_dict.itervalues():
        tx_interval = ChromosomeInterval(tx.chromosome, tx.start, tx.stop, tx.strand)
        if tx_interval.intersection(cgp_interval) is not None:
            r.append([tx, bed_rec])
    return r


def calculate_jaccard(cgp_bed_rec, filtered_tm_txs, min_jaccard, resolve_multiple):
    """calculates jaccard distance. the pybedtools wrapper can't do stranded"""
    results = defaultdict(float)
    with TemporaryFilePath() as cgp, TemporaryFilePath() as tm:
        for tm_tx, tm_bed_rec in filtered_tm_txs:
            with open(cgp, 'w') as outf:
                outf.write(cgp_bed_rec)
            with open(tm, 'w') as outf:
                outf.write(tm_bed_rec)
            cmd = ['bedtools', 'jaccard', '-s', '-a', cgp, '-b', tm]
            r = callProcLines(cmd)
            j = float(r[-1].split()[-2])
            if j >= min_jaccard:
                results[tm_tx.name2] = max(results[tm_tx.name2], j)
    if resolve_multiple is True and len(results) > 1:
        results = dict(sorted(results.iteritems(), key=lambda (gene_id, score): score)[-1])
    return results


def main():
    args = parse_args()
    transmap_dict = get_transcript_dict(args.transmap)
    # pull out best alignment IDs
    best_ids = get_aln_ids(args.ref_genome, args.genome, args.comp_db, best_only=True)
    # filter transMap for large sized transcripts that will mess this up
    transmap_dict = {tx_id: tx for tx_id, tx in transmap_dict.iteritems() if tx_id in best_ids}
    # rename these to the ENSMUSG naming scheme since transMap uses the common names
    transcript_gene_map = get_transcript_gene_map(args.ref_genome, args.comp_db)
    for tx_id, tx in transmap_dict.iteritems():
        tx.name2 = transcript_gene_map[strip_alignment_numbers(tx_id)]
    cgp_dict = get_transcript_dict(args.cgp)
    tm_chrom_dict = create_chrom_dict(transmap_dict)
    cgp_chrom_dict = create_chrom_dict(cgp_dict)
    results_dict = {}
    for chrom, tm_tx_dict in tm_chrom_dict.iteritems():
        for cgp_tx_id, (cgp_tx, cgp_bed_rec) in cgp_chrom_dict[chrom].iteritems():
            filtered_tm_txs = filter_tm_txs(cgp_tx, tm_tx_dict)
            j = calculate_jaccard(cgp_bed_rec, filtered_tm_txs, args.min_jaccard, args.resolve_multiple)
            results_dict[cgp_tx_id] = j
            if args.remove_multiple is True and len(j) > 1:
                continue
            elif len(j) > 0:
                cgp_tx.name2 = ','.join(j.keys())
            else:
                cgp_tx.name2 = cgp_tx.name.split('.')[0]
            print '\t'.join(map(str, cgp_tx.get_gene_pred()))


if __name__ == '__main__':
    main()