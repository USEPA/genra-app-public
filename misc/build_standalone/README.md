## GenRA Standalone Images

This file describes a simplified deployment strategy using pre-built
images, for general development deployment see [Running GenRA, in Docker](../../README.md#running-genra-in-docker)
in the main README.

You should receive the following files:

 - README.md - This file.
 - `genra_app.img.gz` - Docker image for the API container.
 - `genra_ui.img.gz` - Docker image for the UI container.
 - `genra_db.tar.gz` - MongoDB data folder with pre-loaded GenRA data.
 - `standalone.env` - Copy this the `.env`.
 - `docker-compose.yml`
 - `httpd.conf` - Apache configuration file for a proxy to link UI and API.

The GenRA MongoDB data is 32 Gb compressed (as of 2023-7-10), but almost 100 Gb
when uncompressed.

*IN THE FOLDER CONTAINING THE DOWNLOADED FILES*, do the following to 
load the images into your local Docker environment, and unpack the data:
```shell
gzip -d < genra_app.img.gz | docker image load
gzip -d < genra_ui.img.gz | docker image load
# (next two lines should be pasted together, they're a single line really)
docker run -it --rm -v $PWD:/from -v genra_standalone_db:/to \
  genra_app tar vxa --strip-components=1 -C /to -f /from/genra_db.tar.gz
```

With the `.env` file in place use

    docker compose up

to start the GenRA containers.  Browse to `http://127.0.0.1:8448/genra/` to
use GenRA. `Ctrl-C` twice will stop the containers, then

    docker compose down

should be used to clean up to ensure a clean start next time.

You can change the port number and other settings in the `.env` file.

## MongoDB failures in Docker log, how to fix

Occasionally an incomplete shutdown of the MongoDB container will leave
lock files that need to be deleted, try:

```shell
docker run -it --rm -v genra_standalone_db:/to \
  genra_app rm /to/mongod.lock /to/WiredTiger.lock
```

## API for batch processing

Once up and running the container provides and API than can be used
for batch processing.

Note: 127.0.0.1:8448/genra/ is the UI, 127.0.0.1:8447 is the API.

### GET /genra-api/api/genra/v4/chemNN/get_genra_api_api_genra_v4_chemNN

Get nearest neighbors for chem. by FP

This endpoint takes three parameters:

chem_id - the ID of the input chemical

fp - the type of fingerprint to use for similarity searching: chm_mrgn,
chm_httr, chm_ct, chm_aim, bio_txct, bio_txct_ATG, bio_txct_BSK, bio_txct_NVS,
tox_txrf

sel_by - data availability filter, one of tox_txrf, bio_txct, no_filter

e.g. http://127.0.0.1:8447/genra-api/api/genra/v4/chemNN?chem_id=DTXCID30182&fp=chm_mrgn&sel_by=tox_txrf


### GET /genra-api/api/genra/v4/dataMatrix/

Get data availability information (panel 3 in the web. app.).

Parameters as above plus:

k0 - The number of nearest neighbors to return

s0 - The Jaccard similarity threshold

summarise - tox_txrf_dosage, tox_txrf, bio_txct

sumrs_by - How the information will be summarised across the levels of biological organisation
bio_fp, tox_fp, tox_fp_dosage

e.g. http://127.0.0.1:8447/genra-api/api/genra/v4/dataMatrix?chem_id=DTXCID30182&fp=chm_mrgn&sel_by=tox_txrf&k0=5&s0=0.1&summarise=tox_txrf&sumrs_by=tox_fp

### GET /genra-api/api/genra/v4/readAcross/

Similar to dataMatrix but with GenRA prediction included.

Parameters as above plus:

minpos - Minimum positive observations to make a positive prediction

minneg - Minimum negative observations to make a negative prediction

engine - Prediction engine to use, genrapred or genrapy

e.g.  http://127.0.0.1:8447/genra-api/api/genra/v4/readAcross?chem_id=DTXCID30182&fp=chm_mrgn&sel_by=tox_txrf&k0=5&s0=0.1&summarise=tox_txrf&sumrs_by=tox_fp&minpos=0&maxpos=0&engine=genrapy

## Shared access

As configured by default, the web app. is available on all machines on the
network that can see the host.  While examples above often use
127.0.0.1:8448/genra/, while running on a personal Ubuntu desktop host, the
app. was also available on 192.168.1.11:8448/genra/ on a cell phone connected
to the same home wifi network.  192.168.1.11 is the IP address of the host
running Docker on the home network, the address and rules governing visibility
of the host would depend on the networking environment.  The IP address can
be replaced by a machine name like devserver.nihs.nih.gov if available.

## Changing code

Ports (8447, 8448) etc. are configured in docker-compose.yml, httpd.conf, and
standalone.env (copied to .env).  Things define in those files can be changed
without changing the Python code.

The code can be copied to a local folder *while the container is running* with
the docker command:

    docker cp genra_genra_api_1:/genra genra_src

To run the copied code, shut everything down (`docker compose down`), and add
the `volumes:` section (two lines) to the genra_api service definition in
docker-compose.yml as shown:

      genra_api:
        image: genra_app
        env_file: [".env"]
        ports:
          - ${EXT_GENRA_API_PORT}:5000
        volumes:
          - ./genra_src:/genra

Now next time you do `docker compose up` the code being run will be the code
in the local folder ./genra_src.  Depending on configuration you may need to
do `chmod a+rw ./genra_src` so Python can update .pyc files etc.
