batchSystem = parasol
maxThreads = 30
maxCpus = 1024
defaultMemory = 8589934592
jobTree = .jobTree
halJobTree = .halJobTree
log = log.txt
maxJobDuration = 36000
h5prefix = ~

export PYTHONPATH:=./:${PYTHONPATH}
export PATH:=./sonLib/bin:./submodules/jobTree/bin:./hal/bin/:${PATH}

#genomes = C57B6NJ
genomes = Rattus 129S1 AJ AKRJ BALBcJ C3HHeJ C57B6NJ CASTEiJ CBAJ DBA2J FVBNJ LPJ NODShiLtJ NZOHlLtJ PWKPhJ SPRETEiJ WSBEiJ
refGenome = C57B6J

rootDir := $(shell dirname $(realpath $(lastword $(MAKEFILE_LIST))))

dataDir = ${rootDir}/datafiles
annotationBed = ${dataDir}/wgEncodeGencodeBasicVM2.gene-check.bed
gencodeAttributeMap = ${dataDir}/wgEncodeGencodeAttrsVM2.attrs
hal = /cluster/home/jcarmstr/public_html/mouseBrowser_1411/1411.hal
trackHub = trackHub/

all :
	cd sonLib && make
	cd jobTree && make
	cd hal && make
	python lib/twobit/check_if_installed.py; if [ $$? == 3 ]; then python lib/twobit/setup_twobit.py build; python lib/twobit/setup_twobit.py install; fi

run : all
	if [ -d ${jobTree} ]; then rm -rf ${jobTree}; fi
	python src/main.py --refGenome ${refGenome} --genomes ${genomes} --annotationBed ${annotationBed} \
	--dataDir ${dataDir} --gencodeAttributeMap ${gencodeAttributeMap} \
	--maxThreads=${maxThreads} --batchSystem=${batchSystem} --defaultMemory=${defaultMemory} \
	--jobTree ${jobTree} --logLevel DEBUG --maxCpus ${maxCpus} --maxJobDuration ${maxJobDuration} \
	--stats &> ${log}
	if [ -d ${halJobTree} ]; then rm -rf ${halJobTree}; fi
	if [ -d {trackHub} ]; then rm -rf ${trackHub}; fi
	bigBedDirs = /bin/ls -1d output/bedfiles/* | paste -s -d ","
	python hal/assemblyHub/hal2assemblyHub.py ${hal} ${trackHub} --finalBigBedDirs ${bigBedDirs} --noBedLiftover \
	--maxThreads=${maxThreads} --batchSystem=${batchSystem} --defaultMemory=${defaultMemory} \
	--jobTree ${halJobTree} --logLevel DEBUG --maxCpus ${maxCpus} --maxJobDuration ${maxJobDuration} \
	--stats &> ${log}
