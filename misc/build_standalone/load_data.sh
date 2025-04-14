
echo "Processing data files"
for FILE in /tmp/data/*.gz; do \
    echo "Processing $FILE"
    COLLECTION=$(echo $(basename $FILE) | sed -E 's/([^_]+_){2}//; s/\..*//')
    gzip -d < $FILE \
        | mongoimport \
            --uri mongodb://genra_tmp_db/genra \
            --collection $COLLECTION \
            --drop
done
mongosh mongodb://genra_tmp_db/genra --file /tmp/data/_index_db.mongosh

