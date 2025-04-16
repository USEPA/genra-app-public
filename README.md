# genra_app - GenRA api code

## Running GenRA, in Docker

**NOTE:** there are two options for deploying GenRA described here, (1) setting
up a local development environment using Docker, described in this section, or
(2) a pre-built image approach described in
[GenRA Standalone Images](misc/build_standalone/README.md#genra-standalone-images).

 - Copy `template.env` to `.env`

GenRA's Docker deployment supports some optional features:

 - Copy `docker-compose-ui.yml.template` to `docker-compose-ui.yml`<br/>
   if you want to run the UI locally.
 - Copy `docker-compose-mongodb.yml.template` to `docker-compose-mongodb.yml`<br/>
   if you want to run the MongoDB locally. Edit `docker-compose-mongodb.yml` to reflect
   your preference for named docker volume or local bind mount for persistent DB
   storage.
 - Copy `docker-compose-worker.yml.template` to `docker-compose-worker.yml`<br/>
   if you want to run a worker container for fingerprint generation.
   This is required if you want to generate or test fingerprints.
 - Copy `docker-compose-local.yml.template` to `docker-compose-local.yml`<br/>
   if you want to overlay the local file system in the API container,
   typically a developer only use case.  Edit `docker-compose-local.yml` to point to
   your local folder.

Edit `.env` to match you're requirements.

If you are running the UI server locally, you will need to copy
`$GENRA_UI_REPO_PATH/template.env` to `$GENRA_UI_REPO_PATH/.env` and update the latter
to set `APPLICATION_GENRA_API_BASE` to point to something like
`http://127.0.0.1:EXT_GENRA_API_PORT`. "`GENRA_UI_REPO_PATH`" is typically
`../genra-ui`, a clone of the GenRA UI repository in the same folder as your clone of
the GenRA API repository.  `EXT_GENRA_API_PORT` is a setting in `.env`.

If you are running the DB locally, see the section below on loading data into the DB.

Now
```shell
docker compose build
docker compose up -d
```
should build and run the required containers.*  `docker compose down` restarts the
containers from scratch every time it's run.  This wipes some cached data in the Redis
container (safest) but leaves the DB data intact on its persistent volume.  `Ctrl-C`
twice will exit the containers.

For local development without using github docker container registry (ghcr.io), may need to:
```shell
cd genra_base
cp template.env .env
docker build . -t <your_genra_base_name>
```
and then set `GENRA_BASE=<your_genra_base_name>` in `.env`.

View `http://127.0.0.1:EXT_GENRA_API_PORT/apidocs/`, replacing
`EXT_GENRA_API_PORT` with the value used in `.env`, to see the API.

View `http://127.0.0.1:EXT_GENRA_UI_PORT/genra/`, replacing
`EXT_GENRA_UI_PORT` with the value used in `.env`, to see the UI, if
you're running it.  `http://127.0.0.1:EXT_GENRA_UI_PORT/genra/DTXCID30182` will take you
directly to an example chemical.

After Docker images are built and working, you can use
```shell
docker compose up --no-build -d
```
to skip the build step but remember to omit `--no-build` when you make changes requiring
a re-build, such as adding dependencies.

### Loading data into a local MongoDB

If you're restoring an archive file, a command like the following should work:
```shell
docker run -it --rm --network user_default \
    -v /path/to/archive/genra_DEV_mongo.20220119_140724.gz:/in.gz \
    mongo mongorestore --gzip mongodb://user_genra_mongodb_1/genra \
    --archive=/in.gz
```
Replace `user` with your username, and `path/to/archive` with the appropriate
path.

If you're using a copy of Mongo's `/data/db` folder, make sure the correct
content is in the local folder or Docker volume pointed to by the
`GENRA_VOL_MONGODB` variable in `.env`.

### The Jupyter Notebook (Lab) interface

If the `GENRA_DEPLOYMENT_TYPE` variable includes the substring `LOCAL`,
a Jupyter Lab environment will run in the main GenRA container. in
`docker-compose-local.yml` you set the port you want to use on the local
machine, e.g.

```
    ports:
      - 30008:8888
```

`30008` can be whatever you want, don't change the `8888`.

You can get the access token(s) for running Jupyter session(s) with:

```shell
docker exec -it -u 0 <username>_genra_api_1 jupyter server list
```

or by visiting the `.../api/genra/v4/uiJupyter` endpoint.

Normally you could log in to Jupyter lab. at `http://somehost:<port>` where
port is 30008 in the above example.  This is disabled for security reasons in
GenRA, see the `.../api/genra/v4/uiJupyter` endpoint for login directions.

## Developer notes

**WARNING**: (for developers) when you change the API code (or database) you must
completely wipe the Redis container to ensure it's not caching stale function results.
`docker compose down` before `docker compose up`.  `Ctrl-C` or `docker-compose stop` is
not enough.

### Requirements

`requirements.txt` are the pinned versions using
`pip freeze`, `requirements.pip.txt` and `requirements-dev.pip.txt` are the manually
edited "templates", note that a couple of packages have specific versions set there.

**To add a requirement** add it to `requirements.pip.txt` or `requirements-dev.pip.txt`.
Then
```shell
cat requirements.pip.txt requirements-dev.pip.txt > requirements.txt
```
or add it directly to `reqirements.txt` if you don't want to re-pin all requirements.

After building and testing shell into the container and copy
`/requirements.txt.installed` to `/genra/requirements.txt` to pin
all or just the new requirement.

### Fingerprint notes

For each fingerprint, there is a fingerprint class that extends from a base FPGen class.
Fingerprint handling from the python codebase is done through these classes. They are
defined in `genra/lib/fp/` directory; the list of all fingerprint classes can be
seen in `genra/lib/fp/fpclass.py`.

The fingerprint data is stored in GenRA specific mongoDB collections that are constructed
from upstream data sources. Each fingerprint class has a `fp_output_basename` field that
corresponds to the name of the mongo collection name that holds the fingerprint data.

E.g., Bio. (Toxcast) FP are stored in mongo collection `toxcast_fp`, as defined in
`genra/lib/fp/fptoxcast.py`.

#### Generating all fingerprints

**NOTE:** this index is required:
```
db.invitrodb_assay_rslt.createIndex({dsstox_sid: 1})
```

Fingerprints can be generated in new collections which can be checked before
cut-over.  Running the script `./misc/generate_fp_cmds.py` will print bash
commands to copy paste to generate a new set of FP, compare counts with
existing, move existing to `prev_*` and move the new FP into place.  Note all
the final collection names are initially prefixed with `fpgen_` to allow
checking and cut-over.

### Running tests

To run tests we bring up the API container, and then use a second container
using the same image to run tests.

In one shell, bring up the API:
```shell
docker compose --file docker-compose.yml \
    --file docker-compose-local.yml \
    up
```
then in another shell:
```shell
docker compose --file docker-compose.yml \
    --file docker-compose-local.yml \
    run \
    --rm -u `id -u` \
    --e PYTHONPATH=/genra \
    genra_api pytest tests
```
`docker-compose-local.yml`
sets a volume for live code testing.  It tries to set UID, but that only works
for `up`, not `run`, so you still need the `-u` above.

**Note:** for tests marked `very_slow` you need to include the `--very-slow`
flag on the pytest command line for them to run, they're skipped by default.

`docker-compose-local.yml` example:
```yml
version: "3"

services:
  genra_api:
    user: ${UID}
    volumes:
      - ${HOME}/repo/genra/genra_app:/genra
```

Could write a `.sh` file for
this but handy to add flags on the command line like:

```shell
docker compose --file docker-compose.yml \
    --file docker-compose-local.yml \
    run \
    --rm -u `id -u` \
    -e PYTHONPATH=/genra \
    genra_api pytest tests -m 'not slow_api'"
```
to run all tests not marked `slow_api` (defined in `pytest.ini`).

#### "Calibrated" tests

There are a number of UI supporting endpoint tests with the common name prefix
`test_fp_types_results_`.  They compare current results with previously
observed results to catch unexpected changes and allow confirmation (with `git
diff` etc.) that expected changes are as expected.  When intentional changes
have occurred, the reference data (.json files) can be updated by running tests
with the environment variable `CALIBRATE=Y`.  In the above examples,
`-e CALIBRATE=Y`.

It's useful to add the flags `-k test_fp_types_results_ -x` when doing
calibration to avoid running irrelevant tests and exit immediately if a test
fails as no tests should fail during calibration.

As test parameterization changes over time "dead" tests may build up in the
expected results .json files.  To clear these out confirm all tests are
passing, then delete the .json files and run with `CALIBRATE=Y` to generate
files containing only currently active tests.


### Collecting coverage data

Assuming that you're using an overlay file system mounted in the container
at /genra, in the local file system folder corresponding to that, do
```shell
mkdir coverage
mkdir htmlcov
chmod a+rw coverage htmlcov
```
Set the `GENRA_CODE_COVERAGE` variable in `.env` and set
`GUNICORN_CMD_ARGS="--bind=0.0.0.0:5000 --workers=1 --threads 1 --timeout 1800"`.  Use
`http://127.0.0.1:30001/api/genra/v3/manage_coverage/?stop=stop` to end
coverage collection and write the report.

### Generating API spec.

2024-2-13: removed misc/apispec_1.json as new testing procedure requires on-line
spec.  This procedure will still work but the file is no longer needed.

You may want to generate the API spec. with `GENRA_DEPLOYMENT_TYPE=PROD`, which disable
the Swagger UI and the API spec. URL.  In this case use `GENRA_FORCE_SWAGGER=Y` as well
to re-enable the API spec. URL.  `GENRA_SWAGGER_HOST` should also be set to the
host on which scanning will be done.
Then you can update the API spec. with:
```shell
curl http://host:port/apispec_1.json | python -m json.tool > misc/apispec_1.json
```

### Managing MongoDB indexes

With introduction of precalculated neighborhoods (network tool/uiFastNN/fp_info),
the use of indexes to support fast searches of collection has become necessary.
(For reference, compounds=1.13GB, fp_info=28.92GB as of July 12 2022.)

Currently some ChemID fields are being indexed (dsstox_cid, dsstox_sid primarily 
but also name, smiles for compounds collection for ChemID promotion) as well as FP fields in fp_info to be able to quickly run queries on presence of neighborhoods.

Indexes are managed with flask commands. Inside container (with `FLASK_APP` defined), run `flask commands --help` to see list of commands, which includes:
- `flask commands 'show indexes'`
- `flask commands 'create indexes'`

### Running tasks with Celery

Using Celery for parallel processing has various advantages.  Potentially, it
can scale to multi-host processing, although firewall rules currently seem to
block `redis://mymachine.myorg.com/0` as a message broker URL, so we
use `redis://redis:6379/0` and rely on being on the same docker network
for now.

On a single host, a single celery worker by default uses multiprocessing to run
as many processes as there are cores on the host.  We can run the worker with
`--concurrency 1` to only run one process per Docker container.  This would
allow using container level isolation to avoid issues with running Corina in
parallel processes for example.  I.e. running four worker containers,
rather than one worker container running four processes.

We use Redis as the message broker back-end.  Could switch to RabbitMQ if
needed, but Redis has other uses.

For anything to work, Redis needs to be running.  Currently it runs by default
with the rest of the containers on `docker compose up`, but can be started by
itself.

Run Redis
```
docker compose \
    --file docker-compose.yml \
    --file docker-compose-local.yml \
    up redis
```

You can load tasks without starting any workers, the tasks just sit on the
queue waiting for workers.  Loading ~1.4M DTXCID values in 10,000 DTXCID
batches takes less than 20 seconds.

Load example tasks

```
docker compose --file docker-compose.yml \
    --file docker-compose-local.yml \
    --file docker-compose-worker.yml \
    run --rm -u `id -u` genra_api \
    python genra/run_tasks.py
```

If you chose to have a worker container created in the section on
running GenRA in Docker, there will already be one worker container
running to process jobs on the host running the API container.  This may
be all you need.  To start a worker container manually, or to start
additional worker containers:

Create worker

```
docker compose \
    --file docker-compose.yml \
    --file docker-compose-worker.yml \
    run --rm -u `id -u` genra_api \
    celery -A genra.genra_celery worker -l INFO
```

Debugging in celery+Docker

To debug within a Celery worker, drop `from celery.contrib import rdb; rdb.set_trace()`. Run the applicable
piece of code. Get the port number that the debugger is published to -
`docker logs <worker_container_name> | grep 'Ready to connect'` will output something like
`Remote Debugger:6927: Ready to connect: telnet 127.0.0.1 6927`. Shell into the worker container, and run
the provided telnet command. (May have to `apt-get install telnet` first, or use Python's telnet package.)

### Preaclc module/Updating fp_info

**UPDATE: see also [precalc_hpc/README.md](./genraweb/lib/fp/precalc_hpc/README.md) for HPC version of precalc.**

Precalc module (genraweb/lib/fp/precalc/) updates the fp_info collection so that it holds precalculated 
neighborhood data for every chemical, for all applicable FPs. This data gets used by the
neighborhood explorer (uiFastNN), and also by searchFP if target is not custom SMILEs.
Initially this was done using the existing mongo infrastructure (searchFP in batches), however,
using scikit.NearestNeighbors module proved to be a lot faster due to the ability to configure
multiprocessing and avoid DB IO costs. 

Precalc is done in two parts: chunkified approach for all chemical FPs + no_filter combinations, and 
all-at-once approach for other combinations (incl. chemical FPs + filter and non-chemical FPs + no_filter).

#### Chemical FPs + no_filter combinations:

With AIM FP as example, create `precalc_chm_aim.py` with 
```
from genraweb.lib.fp.precalc.precalc import precalculate
precalculate(["chm_aim"], ["no_filter"])
```
Invoke that file from inside a separate docker container:
```
docker compose --file docker-compose.yml \
    --file docker-compose-local.yml \
    run \
    --rm -u `id -u` --name precalc_chm_aim -d \
    genra_api bash -c "python3 precalc_chm_aim.py"
```

#### Other combinations (incl. chemical FPs + filter and non-chemical FPs + no_filter):

Shell into an already running API container with
```
docker exec -it <genra_api_container_name> -u `id -u` sh
```
and run `flask commands precalculate`; there will be granular options available that can be displayed
with `flask commands precalculate --help`.

#### Legacy precalc

Documentation to invoke the mongo approach (this approach is no longer used).

WARNING: if you generate fp_info with FPs with restricted distribution on dev and copy
to staging / prod., remember to remove restricted data, e.g.:

```
db.fp_info.updateMany({}, {$unset: {bio_htpp_MCF7: true, bio_htpp_U2OS: true}})
```

WARNING: unlike FP generation, NN counting always writes to the "live" collection, `fp_info`.

UPDATE: env. var. `GENRA_FP_INFO_COLLECTION` can be used to read / write other than `fp_info`.

The `fp_info` collection holds information about FPs by chemical, in particular the
number of neighbors, which is expensive to calculate on the fly.  For HTPP, the four
variations can be calculated with:

```
http://localhost:30001/genra-api/api/genra/v3/genFP/?sidsList=ALL&fp_type=bio_htpp_MCF7&what=nnn&sel_by=no_filter
http://localhost:30001/genra-api/api/genra/v3/genFP/?sidsList=ALL&fp_type=bio_htpp_U2OS&what=nnn&sel_by=no_filter
http://localhost:30001/genra-api/api/genra/v3/genFP/?sidsList=ALL&fp_type=bio_htpp_U2OS&what=nnn
http://localhost:30001/genra-api/api/genra/v3/genFP/?sidsList=ALL&fp_type=bio_htpp_MCF7&what=nnn
```

which defaults to `sel_by=tox_txrf` and `s0=0.1` when not specified.

#### fp_info metadata

Making a separate query of the `compounds` collection in `uiFastNN()` is
a noticeable slow down.  So instead copy relevant fields into `fp_info`
collection.

This is the same query run twice, once for `dsstox_sid` and once for
`dsstox_cid`. `...update(...$lookup...` seems more intuitive than
`...aggregate(...$merge...` but `$lookup` is not supported in `update()`.

```mongodb
db.fp_info.aggregate(
    [
        {"$match": {"dsstox_sid": {"$ne":null}}},
        {
            "$lookup": {
                "from": "compounds",
                "localField": "dsstox_sid",
                "foreignField": "dsstox_sid",
                "as": "chem",
            }
        },
        {
            "$merge": {
                "into": "fp_info",
                "whenMatched": [
                    {"$addFields": {
                        "smiles": {"$first": "$$new.chem.smiles"},
                        "casrn": {"$first": "$$new.chem.casrn"},
                        "mol_weight": {"$first": "$$new.chem.mol_weight"},
                        "monoisotopic_mass": {"$first": "$$new.chem.monoisotopic_mass"},
                        "name": {"$first": "$$new.chem.name"},
                        "dsstox_cid": {"$first": "$$new.chem.dsstox_cid"},
                    }}
                ],
                "whenNotMatched": "discard",
            }
        },
    ]
)
db.fp_info.aggregate(
    [
        {"$match": {"dsstox_cid": {"$ne":null}}},
        {
            "$lookup": {
                "from": "compounds",
                "localField": "dsstox_cid",
                "foreignField": "dsstox_cid",
                "as": "chem",
            }
        },
        {
            "$merge": {
                "into": "fp_info",
                "whenMatched": [
                    {"$addFields": {
                        "smiles": {"$first": "$$new.chem.smiles"},
                        "casrn": {"$first": "$$new.chem.casrn"},
                        "mol_weight": {"$first": "$$new.chem.mol_weight"},
                        "monoisotopic_mass": {"$first": "$$new.chem.monoisotopic_mass"},
                        "name": {"$first": "$$new.chem.name"},
                        "dsstox_sid": {"$first": "$$new.chem.dsstox_sid"},
                    }}
                ],
                "whenNotMatched": "discard",
            }
        },
    ]
)
```

### Stand-alone notes

Overall strategy is to distribute pre-built images such that the end-user only
needs to install Docker and docker-compose, and then run `docker compose up` in
the directory containing the `docker-compose.yml`. See [GenRA Standalone
Images](misc/build_standalone/README.md#genra-standalone-images) for end-user instructions.

- The `genra_app` image can be built with `version.txt` set to the desired
version, but note that the text is only used up to the first dash.

```shell
    git describe --match '[0-9]*' --dirty >/tmp/vt.tmp
    sed 's/-dirty/+edits/; s/-/_/g' </tmp/vt.tmp >version.txt
```

provides detailed content.  GenRA 3.2 and subsequent dev commits used the above
directly to read the version from '.git', but this requires '.git', and therefore
any remote access tokens etc., to be present in the image.  Consider which version
of the code you want to build the image from, dev or main - the recipient will be able
to change `GENRA_DEPLOYMENT_TYPE` from `PROD` to `DEV`, which can make experimental
features available, although the data will not be present in the DB.

**FOR SECURITY:** Remove any stray log files etc. when
building the image for distribution.  Also copy `standalone.env` to `.env`
which ensures DB credentials are not in the image and builds on `python:3.x`
rather than the internal base image which includes Corina.

- The `genra_ui` image needs to be
built with `APPLICATION_GENRA_API_BASE = /genra-api` so the Apache proxy can
link the UI and API, as the UI (Nuxt) can't read an env. var. at run time for
the API URL.

The `genra_mongo` image requires a multi-step process to build.

- Dump the MongoDB collections you want to include:
- First, create the `_dump_db.sh` and `_index_db.mongosh` files.  Set
  `GENRA_DEPLOYMENT_TYPE` to match the DB environment you want to dump.  For
  example, to dump the `PROD` DB, set it to `PROD`.  This avoids
  `_index_db.mongosh` including instructions to index collections that aren't
  being dumped. E.g. running as `DEV` will create indexes for experimental FP
  collections not included in the `PROD` DB dump.

```shell
docker compose --file docker-compose.yml --file docker-compose-local.yml --file docker-compose-ui.yml \
  run --rm -u `id -u` -e PYTHONPATH=/genra genra_api python misc/build_standalone/dump_db.py
```

- Then run the dump:

```shell
mkdir datadump
mv _dump_db.sh _index_db.mongosh datadump
cd datadump
bash _dump_db.sh
cd ..

cp misc/build_standalone/load_data.sh datadump
mkdir genra_db
chmod 777 genra_db
docker network create genra_tmp_db_nw
docker run -u `id -u` --name genra_tmp_db --network genra_tmp_db_nw -v $PWD/genra_db:/data/db -d mongo
docker run --rm --network genra_tmp_db_nw -it -v $PWD/datadump:/tmp/data mongo bash /tmp/data/load_data.sh
docker run --rm --network genra_tmp_db_nw -it mongo mongosh mongodb://genra_tmp_db:27017/genra
# show collections, db.compounds.getIndexes() etc.
docker stop genra_tmp_db
docker rm genra_tmp_db
docker network rm genra_tmp_db_nw
chmod 755 genra_db
```

- Save the images / data:

```shell
docker image save genra_app | gzip > genra_app.img.gz
docker image save genra_ui | gzip > genra_ui.img.gz
tar vcaf genra_db.tar.gz genra_db
```

- Upload the saved images plus `httpd.conf`, `docker-compose-standalone.yml`,
  renamed to `docker-compose.yml`, and `standalone.env` somewhere accessible to
  the end-user.

TODO: `docker save / load` turns out to be very inefficient, consider using
zipped data dir for mongo, or a docker repository.

#### Older notes for stand alone dev. env.

For the UI container, after copying `template.env` to `.env`, only
`APPLICATION_GENRA_API_BASE` needs changing, to something like
`http://127.0.0.1:30001/genra-api`.

If images / containers are built / created with names prefixed with a literal
`user_` rather than the intended `<actual_username>_`, make sure you're using
the latest available `docker compose`, at least 1.29.2.  If necessary do:

```shell
python -m venv venv_genra
. venv_genra/bin/activate
pip install docker-compose
```

In RedHat, quoted `GUNICORN_CMD_ARGS` in the `genra_app` `.env` file seemed ok, in Ubuntu quotes need to be removed (which seems to match `docker-compose` docs.).

Note that tests will fail unless your DB dump includes all tables used for testing in
dev.

### Versioning

This is a copy of commit notes for reference:

This code relies on the .git folder being present in /genra in the
container.

Remember to do `git push origin --tags` after tagging.

If we want dev and stg to show a sensible value for this we need to
tag a commit that is an ancestor of dev, i.e. was dev at some point,
tagging the stg -> main merge commit doesn't do this. You can find a
good common ancestor with:

    git merge-base dev main

*but* this means `main` will report as 3.0-8-g7d3d857 where the 8 extra
commits are dev->stg and stg->main merges etc.

Workaround: tag the stg->main merge commit 3.0 so main reports cleanly
as 3.0, and tag the common ancestor, found with `git merge-base dev main`
as 3.0_dev.

Non version tags can be filtered out with

    git describe --match "[0-9]*"
    3.0-67-g7d3d857

feature/GEN-793-add-endpoint-to-report-version

### Profiling endpoints

Profiling the Flask endpoints can be done with some minor adjustments.

First, remove HEALTHCHECK line from Dockerfile - otherwise, these requests will clog data folder.

Create data directory `/profiler` at project root, and add the configuration right below `app` instance:

    app = Flask(__name__)
    from werkzeug.middleware.profiler import ProfilerMiddleware
    app.wsgi_app = ProfilerMiddleware(app.wsgi_app, profile_dir='/genra/profiler')

Make desired requests to Flask app, which will be logged in the `/profiler` directory. If this is inside the docker container, may need to first `docker cp .../genra/profiler ...` to put it on host filesystem.

To visually interact with the profiled data, use the `snakeviz` python package and view it on browser:
```shell
python3 -m venv venv_profiler
pip install snakeviz
snakeviz -p <desired port> --server /path/to/profiler/directory
```
# Disclaimer:
The United States Environmental Protection Agency (EPA) GitHub project code is provided on an "as is" basis and the user assumes responsibility for its use.
EPA has relinquished control of the information and no longer has responsibility to protect the integrity, confidentiality, or availability of the information.
Any reference to specific commercial products, processes, or services by service mark, trademark, manufacturer, or otherwise, does not constitute or imply
their endorsement, recommendation or favoring by EPA. The EPA seal and logo shall not be used in any manner to imply endorsement of any commercial product or
activity by EPA or the United States Government. 
