```shell
# In monogosh
db.fp_info.updateMany({}, {$unset: {chm_aim: true}})

# In shell
docker rm "precalc_chm_aim"
docker compose --file docker-compose.yml --file docker-compose-local.yml \
    --file docker-compose-ui.yml --file docker-compose-worker.yml \
    run --rm -u `id -u` \
    --name precalc_chm_aim -d -e PYTHONPATH=/genra genra_api bash -c \
    "python3 misc/tickets/GEN-1034-re-pre-calc-aim-fp/precalc.py"
docker logs precalc_chm_aim
```
