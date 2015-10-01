"""
jobTree wrapper for AugustusTMR.
"""

import os
import argparse
import shutil
import itertools
import sqlite3 as sql
from pyfaidx import Fasta
from jobTree.scriptTree.target import Target
from jobTree.scriptTree.stack import Stack
from sonLib.bioio import system, popenCatch, getRandomAlphaNumericString
from lib.sequence_lib import GenePredTranscript
from lib.general_lib import mkdir_p


#####
# Below are hard coded commands and paths to run Augustus and related scripts.
#####
padding = 20000
max_gene_size = 2000000
tm_2_hints_params = ("--ep_cutoff=0 --ep_margin=12 --min_intron_len=40 --start_stop_radius=5 --tss_tts_radius=5 "
                    "--utrend_cutoff=6 --in=/dev/stdin --out=/dev/stdout")
tm_2_hints_script = "augustus/transMap2hints.pl"
tm_2_hints_cmd = " ".join([tm_2_hints_script, tm_2_hints_params])

hints_db = "/hive/groups/recon/projs/mus_strain_cactus/pipeline_data/comparative/1509/augustus/hints/1509.aug.hints.db"
hints_db_query = '''select source,typename,start,end,score,strand,frame,priority,grp,mult,esource
      FROM hints,featuretypes
      WHERE hints.speciesid IN (SELECT speciesid FROM speciesnames WHERE speciesname="{genome}")
             AND seqnr IN (SELECT seqnr FROM seqnames WHERE speciesid IN (SELECT speciesid FROM speciesnames WHERE speciesname="{genome}") AND seqname="{chrom}")
             AND start >= {start} AND end <= {stop} AND typeid=type'''

augustus_bin = "/cluster/home/mario/augustus/trunks/bin/augustus"
augustus_base_cmd = ("{fasta} --predictionStart=-{start} --predictionEnd=-{start} --extrinsicCfgFile={cfg} "
                     "--hintsfile={hints} --UTR=on --alternatives-from-evidence=0 --species=human "
                     "--allow_hinted_splicesites=atac --protein=0 --/augustus/verbosity=1 --softmasking=1 "
                     "--outfile=/dev/stdout")
augustus_cmd = " ".join([augustus_bin, augustus_base_cmd])

cfgs = {1: "etc/extrinsic.ETM1.cfg", 2: "etc/extrinsic.ETM2.cfg"}


def attach_database(path):
    con = sql.connect(path)
    cur = con.cursor()
    return con, cur


def get_transmap_hints(gp_string):
    """
    Uses transMap2hints.pl to create a hints file from a genePred
    """
    return popenCatch(tm_2_hints_cmd, stdinString=gp_string)


def parse_rnaseq_query(query, chromosome, priority=3):
    """
    Parses the results from the sqlite database into a gff-like format
    """
    for source, typename, start, end, score, strand, frame, _, grp, mult, esource in query:
        tags = "pri={};src={};mult={};".format(priority, esource, mult)
        yield "\t".join(map(str, [chromosome, source, typename, start, end, score, ".", ".", tags])) + "\n"


def get_rnaseq_hints(genome, chrom, start, stop):
    """
    Extracts the RNAseq hints from the database
    """
    this_db_query = hints_db_query.format(genome=genome, chrom=chrom, start=start, stop=stop)
    con, cur = attach_database(hints_db)
    query = cur.execute(this_db_query)
    rnaseq_hint = "".join(list(parse_rnaseq_query(query, chrom)))
    return rnaseq_hint


def write_hint_fasta(hint, seq, chrom, tmp_dir):
    """
    Writes the hints and the seq to a file to be used by Augustus.
    """
    hint_f = os.path.join(tmp_dir, getRandomAlphaNumericString(10) + ".gff")
    seq_f = os.path.join(tmp_dir, getRandomAlphaNumericString(10) + ".fa")
    with open(hint_f, "w") as hint_fh, open(seq_f, "w") as seq_fh:
        hint_fh.write(hint)
        seq_fh.write(">{}\n{}\n".format(chrom, seq))
    return hint_f, seq_f


def rename_transcripts(transcripts, cfg_version, name):
    """
    Renames overlapping transcripts augIX-ID, where X is the index of the extrinsic.cfg file, e.g. 1 or 2 and where
    ID is the transmap alignment ID, use augIX-n-ID if more than 1 transcript overlaps the alignment
    """
    name_map = {}
    for i, x in enumerate(transcripts):
        if i > 0:
            name_map[x] = "augI{}-{}-{}".format(cfg_version, i + 1, name)
        else:
            name_map[x] = "augI{}-{}".format(cfg_version, name)
    return name_map


def write_augustus(r, name_map, out_path, start_offset):
    """
    Writes the results of AugustusTMR to a file.
    """
    with open(out_path, "w") as outf:
        for x in r:
            if x.startswith("#"):
                continue
            if "AUGUSTUS" in x:
                x = x.split("\t")
                if x[2] in ["exon", "CDS", "start_codon", "stop_codon"]:
                    t = x[-1].split()
                    n = t[-3].split('"')[1]
                    t[-1] = t[-3] = '"{}";'.format(name_map[n])
                    t = " ".join(t)
                    x[3] = int(x[3]) + start_offset
                    x[4] = int(x[4]) + start_offset
                    x[-1] = t
                    outf.write("\t".join(map(str, x)) + "\n")


def run_augustus(target, hint_f, seq_f, name, start, stop, aln_start, aln_stop, cfg_version, cfg_path, out_tmp_dir):
    """
    Runs Augustus for each cfg/gp_string pair.
    """
    cmd = augustus_cmd.format(fasta=seq_f, start=start, stop=stop, cfg=cfg_path, hints=hint_f)
    r = popenCatch(cmd)
    r = r.split("\n")
    # extract only the transcript lines
    l = [x.split() for x in r if "\ttranscript\t" in x]
    # filter out transcripts that do not overlap the alignment range
    transcripts = [x[-1] for x in l if not (int(x[4]) < start or int(x[3]) > stop)]
    # if we lose everything, stop here
    if len(transcripts) > 0:
        # rename transcript based on cfg version, and make names unique
        name_map = rename_transcripts(transcripts, cfg_version, name)
        # write this to a shared location where we will combine later
        out_path = os.path.join(out_tmp_dir, getRandomAlphaNumericString(10) + ".gff")
        write_augustus(r, name_map, out_path, start)


def transmap_2_aug(target, gp_string, genome, sizes_path, fasta_path, out_tmp_dir):
    """
    Runs Augustus on one individual genePred string. Augustus is ran with each cfg file in cfgs
    """
    fasta = Fasta(fasta_path)
    chrom_sizes = {x.split()[0]: x.split()[1] for x in open(sizes_path)}
    gp = GenePredTranscript(gp_string.rstrip().split("\t"))
    # ignore genes with no coding region or longer than max_gene_size
    if not (gp.thickStart >= gp.thickStop or gp.stop - gp.start > max_gene_size):
        chrom = gp.chromosome
        start = max(gp.start - padding, 0)
        stop = min(gp.stop + padding, chrom_sizes[chrom])
        tm_hint = get_transmap_hints(gp_string)
        rnaseq_hint = get_rnaseq_hints(genome, chrom, start, stop)
        hint = "".join([tm_hint, rnaseq_hint])
        seq = fasta[chrom][start:stop]
        hint_f, seq_f = write_hint_fasta(hint, seq, chrom, target.getGlobalTempDir())
        for cfg_version, cfg_path in cfgs.iteritems():
            target.addChildTargetFn(run_augustus, memory=8 * (1024 ** 3),
                                    args=[hint_f, seq_f, gp.name, start, stop, gp.start, gp.stop,
                                          cfg_version, cfg_path, out_tmp_dir])


def cat(target, genome, output_gp, out_tmp_dir):
    """
    Concatenates all of the results into one big genePred, and sorts it by chromosome/pos
    """
    files = os.listdir(out_tmp_dir)
    results = [l.split() for f in files for l in open(os.path.join(out_tmp_dir, f))]
    results = sorted(results, key=lambda x:(x[0], x[3]))
    with open(output_gp, "w") as outf:
        for x in results:
            outf.write("\t".join(x) + "\n")


def wrapper(target, input_gp, output_gp, genome, sizes_path, fasta_path):
    """
    Produces one jobTree target per genePred entry. In the future, we could try chunking this per target but during
    initial testing I found that it takes ~15 seconds to extract the RNAseq hints and ~1 minute to run each Augustus
    instance. This seems to be a good time per job to me.
    """
    out_tmp_dir = target.getGlobalTempDir()
    for line in open(input_gp):
        target.addChildTargetFn(transmap_2_aug, args=[line, genome, sizes_path, fasta_path, out_tmp_dir])
    target.setFollowOnTargetFn(cat, args=[genome, output_gp, out_tmp_dir])


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--inputGp", required=True)
    parser.add_argument("--outputGp", required=True)
    parser.add_argument("--genome", required=True)
    parser.add_argument("--chromSizes", required=True)
    parser.add_argument("--fasta", required=True)
    Stack.addJobTreeOptions(parser)
    args = parser.parse_args()
    i = Stack(Target.makeTargetFn(wrapper, args=(args.inputGp, args.outputGp, args.genome, 
                                                 args.chromSizes, args.fasta))).startJobTree(args)
    if i != 0:
        raise RuntimeError("Got failed jobs")


if __name__ == '__main__':
    from augustus.run_augustus import *
    main()
