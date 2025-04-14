Code to make a small DB for security scanning purposes.

[`./small_db.py`](./small_db.py) has a list of compounds and fingerprints and works out
the set of compounds that are neighbors of those compounds for those fingerprints, and
writes just those compounds to a second database.

Not really automated because this will be done rarely, but basic procedure is:

 - Run the API container "normally" pointing to the appropriate CCTE MongoDB.
 - Run a local MongoDB.  The service host name should be `genra_mongodb`.
 - Run small_db.py.
 
Can be run from bash prompt in API container in /genra folder with
```shell
PYTHONPATH=. conda run --no-capture-output -n genra python misc/small_db/small_db.py
# or
docker compose --file docker-compose.yml --file local-docker-compose.yml \
     --rm -u `id -u` genra_api bash -c \
     "PYTHONPATH=. conda run --no-capture-output -n genra python misc/small_db/small_db.py"
```

 - This will **drop** and recreate required tables in the local MongoDB.
 - It checks the reference DB and the destination DB are not the same, so damaging
 regular DB data is unlikely.
 - To use the new small DB, set GENRA_DB_ environment variables appropriately.

The above will work with the local MongoDB set up according to GenRA's main README,
you'll end up with the small DB data in which ever folder or Docker volume you
configured for the `genra_mongodb` service.

But it's convenient to make a special docker image that contains the small DB data.
But see <https://stackoverflow.com/a/59071962/1072212> - the default MongoDB image with
no external volume will not persist data.  So, following the workaround:

Set genra_settings.py to point at the reference CCTE MongoDB, and
use a special `docker-compose-mongodb.yml`
like this:
```dockerfile
version: "3"

services:
  genra_mongodb:
    image: mongo:latest
    command: bash -c "mkdir -p /persist_in_img && mongod --dbpath /persist_in_img --noauth --bind_ip_all"
```
Then:
 - Run `small_db.py` as above.
 - Find the name of the container running the MongoDB.
 - `docker commit <name> genra_smalldb`
 - Update `docker-compose-mongodb.yml` to read
```dockerfile
version: "3"

services:
  genra_mongodb:
    image: small_db
    command: bash -c "mongod --dbpath /persist_in_img --noauth --bind_ip_all"
```
 - Update `.env` to use the small DB, something like:
```shell
# small db
GENRA_DB_DB=genra
GENRA_DB_HOST=genra_mongodb
GENRA_DB_PASS=
GENRA_DB_PORT=27017
GENRA_DB_USER=
GENRA_DB_USE_URI=Y
```
