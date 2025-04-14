
FPS="chm_mrgn chm_httr chm_aim chm_ct"
FILTERS="bio_txct tox_txrf no_filter"

FILTERS="bio_txct tox_txrf pesticideRAC"

FPS="chm_phch"
# FILTERS="no_filter"

for FP in $FPS; do
        for FILTER in $FILTERS; do
                echo $FP $FILTER
                cat sbatch.sh >subtmp.sh
                cat fast_jaccard.env >>subtmp.sh
cat >>subtmp.sh << EOT 

# $(date)                
export FJ_FP_ID=$FP
export FJ_SEL_BY=$FILTER
export FJ_COLLECTION=fj_$FP"_"$FILTER
export FJ_INIT=run
EOT
                cat submit.sh >>subtmp.sh
                sbatch --array 0-6 subtmp.sh
                sleep 2
        done
done

