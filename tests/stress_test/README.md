# Stress testing with Locust

## Use

Locust is a Python-based stress testing tool.  It runs a web UI
on port 8089.

Locust workers launched before the master don't seem to connect, so
first:

    locust --master

in one shell, then

    for i in 1 2 3 4 5; do locust --worker & done

in another. (May need to add `-f 'tests/stress_test/locustfile'` option.)

To kill all locusts:

    ps waux | grep locust | sed 's/[^ ]* \+//; s/ .*//' | xargs kill

### UNSAFE_LEGACY_RENEGOTIATION_DISABLED issue

As of 2023-05-22 Locust is refusing to connect to comptox.epa.gov because
`UNSAFE_LEGACY_RENEGOTIATION_DISABLED`, and Chrome is reporting:
    Connection - obsolete connection settings
    The connection to this site is encrypted and authenticated using TLS 1.2,
    RSA, and AES_256_CBC with HMAC-SHA1.
    - RSA key exchange is obsolete. Enable an ECDHE-based cipher suite.
    - AES_256_CBC is obsolete. Enable an AES-GCM-based cipher suite.
Workaround from https://stackoverflow.com/questions/71603314
    PYTHONPATH=~/repo/genra/genra_app OPENSSL_CONF=$PWD/openssl.cnf locust
where `openssl.cnf` is in this folder.

### Unique chemicals

If a file `ids.lst` exists in the directory containing `locust(_ui).py`, it
will be used as a source of chemical IDs to make each set of requests unique.
Delete or rename it to disable it and default to repeatedly using the BPA ID
"DTXCID30182".  To create a new `ids.lst`:

```python
from genraweb.resources import DB
ids = [i.get("dsstox_cid") for i in DB.fp_info.find({}, {"_id":0, "dsstox_cid":1})]
ids = set(ids)
ids = [i for i in ids if str(i).startswith("DTXCID")]
open("ids.lst", "w").write("\n".join(ids))
```

Chemical IDs which generate a 400 or 500 series response will appear
as errors in the Locust UI.  So pull CID only from fp_info, rather than
SIDs and CIDs from compounds, to minimize the number of errors.

## Results

Turning off the Redis cache has a huge impact as expected and approximates
users selecting different chemicals all the time.

Upping the threads in green unicorn to 40 from 4 helps a lot.  More workers
would probably help too, only tested on 8 cores so not verified.
