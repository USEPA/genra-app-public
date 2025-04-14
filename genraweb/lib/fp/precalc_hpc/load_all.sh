# Demo script for loading all fj_ data to fp_info
export GENRA_FP_INFO_COLLECTION=fp_info_2024
echo -e 'y\nn\ny' | python fast_jaccard.py load fj_chm_phch_bio_txct
echo -e 'y\nn\ny' | python fast_jaccard.py load fj_chm_phch_no_filter
echo -e 'y\nn\ny' | python fast_jaccard.py load fj_chm_phch_pesticideRAC
echo -e 'y\nn\ny' | python fast_jaccard.py load fj_chm_phch_tox_txrf
