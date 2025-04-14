#!/usr/bin/bash
GENRA_DIR=/home/tbrown02/fast_jaccard/genra_app
FJ_DIR=$GENRA_DIR/genraweb/lib/fp/precalc_hpc
FJ_INIT=${FJ_INIT:-run}
date
# See $FJ_DIR/README.md to generate condainit.sh
export OPENBLAS_NUM_THREADS=1
export MKL_NUM_THREADS=1
srun bash -c "\
   source $FJ_DIR/condainit.sh ; conda activate genra ; \
   set | grep FJ_ ; \
   PYTHONPATH=$GENRA_DIR python -u $FJ_DIR/fast_jaccard.py $FJ_INIT \
   "
date
