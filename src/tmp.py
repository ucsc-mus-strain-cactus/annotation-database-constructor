import os

import lib.sequence_lib as seq_lib
import lib.psl_lib as psl_lib
import lib.sqlite_lib as sql_lib
from src.abstractClassifier import AbstractClassifier
from collections import defaultdict, Counter
from src.helperFunctions import *
from itertools import izip


#transcripts = seq_lib.getGenePredTranscripts("/cluster/home/ifiddes/mus_strain_data/pipeline_data/comparative/1504/transMap/2015-05-28/transMap/C57B6NJ/transMapGencodeBasicVM4.gp")
transcripts = seq_lib.getGenePredTranscripts("/cluster/home/ifiddes/mus_strain_data/pipeline_data/comparative/1504/transMap/2015-05-28/transMap/PAHARIEiJ/syn/transMapGencodeBasicVM4.gp")
transcriptDict = seq_lib.transcriptListToDict(transcripts, noDuplicates=True)
annotations = seq_lib.getGenePredTranscripts("/cluster/home/ifiddes/mus_strain_data/pipeline_data/comparative/1504/transMap/2015-05-28/data/wgEncodeGencodeBasicVM4.gp")
annotationDict = seq_lib.transcriptListToDict(annotations, noDuplicates=True)
#alignments = psl_lib.readPsl("/cluster/home/ifiddes/mus_strain_data/pipeline_data/comparative/1504/transMap/2015-05-28/transMap/C57B6NJ/transMapGencodeBasicVM4.psl")
alignments = psl_lib.readPsl("/cluster/home/ifiddes/mus_strain_data/pipeline_data/comparative/1504/transMap/2015-05-28/transMap/PAHARIEiJ/syn/transMapGencodeBasicVM4.psl")
alignmentDict = psl_lib.getPslDict(alignments, noDuplicates=True)
seqDict = seq_lib.getSequenceDict("/cluster/home/ifiddes/mus_strain_data/pipeline_data/assemblies/1504/PAHARIEiJ.fa")

aId = "ENSMUST00000165720.2-1"
t = transcriptDict[aId]
a = annotationDict[psl_lib.removeAlignmentNumber(aId)]
aln = alignmentDict[aId]

deletions = [seq_lib.chromosomeRegionToBed(t, start, stop, "0", "A") for start, stop, size in deletionIterator(a, t, aln, mult3) if start >= t.thickStart and stop < t.thickStop]