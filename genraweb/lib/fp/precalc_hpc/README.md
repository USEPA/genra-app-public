# HPC nearest neighbor pre-calc. / fp_info update.

`precalc_hpc` contains [fast_jaccard.py](./fast_jaccard.py), a simple numpy based Jaccard
and cosine similarity calculation
tool intended to be run on an HPC cluster or other multi-node environment.
It uses a mongodb database to store jobs to be run.

As of 2023-04-28 this code is processing 0.28 chemicals per second per process, or
about 1.7 million chemicals in 7 hours on 8 nodes (8x31 cores) of an HPC cluster.

## TODO:

* [x] Handle filters in init phase.  
      Sort to beginning of array?
* [x] Load results into fp_info.
* [x] Add created / started / completed timestamps to metadata record.
* [x] Use SLURM_NODEID to stagger job starts to separate job reads from db.  
      Somewhat unclear how that will play with SLURM scheduling.

## Step 0: generate list of jobs.

Tech. Note: rather than making this a separate step we could use SLURM_NODEID
to have the "first" job build the collection if it doesn't exist, and have
other jobs wait until it does but there's some complexity there and if it fails
HPC nodes will be sitting idle.  So better to make it a separate supervised
step.

### Using `flask commands precalculate` (recommended).

First, manually (using MongoDB admin. of some kind) drop any existing
fj_<FP_ID>_<FILTER_ID> collection that already exists.

Then see the [main README](../../../../README.md) for notes on using the
multi-purpose `flask commands` in the GenRA environment.  Run `flask commands
precalculate` to be guided through creation of the job lists.  This approach
can set up job lists for multiple FPs and filters at once.

### Not using `flask commands precalculate` (not recommended).

These next steps are what `flask commands precalculate` does under the hood,
use that instead.  These steps only generate one FP / FILTER  pair at a time.

The first step is to generate a list of jobs to be run. This can be done in any
environment, it's a single process.  Copy `fast_jaccard.env.template` to
`fast_jaccard.env` and edit it to point to your MongoDB instance.  Set
`FJ_FP_ID` and `FP_SEL_BY` appropriately.  Then

    source fast_jaccard.env ; python fast_jaccard.py init

This will fail if the collection `fj_$FJ_FP_ID"_"$FJ_SEL_BY` already exists.

### Description of job list documents.

Each job list collection contains a single metadata record:

    genra> db.fj_chm_httr_no_filter.findOne({metadata:true})

```json
{
  "metadata": true,
  "fp_id": "chm_httr",
  "sel_by": "tox_txrf",
  "batch_size": 1000,
  "bit_names": [
    "httr_0",    "httr_1",    "httr_10",   "httr_100",  "httr_1000",
    "httr_1001", "httr_1002", "httr_1003", "httr_1004", "httr_1005",
    "... lots more items"
  ],
  "max_block": 1628,
  "rows": 1628053,
  "log": ["Mon May  1 19:26:16 2023 This collection created"],
  "in_filter": 977
}
```

And a number of "job" records which have the `done` key (`bits` shortened for layout):

    genra> db.fj_chm_httr.no_filter.findOne({done:false})

```json
{
  "block_i": 61,
  "done": false,
  "reserved": true
  "chems": [
    "DTXCID101123579", "DTXCID101123581", "DTXCID101123662", "DTXCID101123674",
    "DTXCID101123686", "DTXCID101123717", "DTXCID101123755", "DTXCID101123767",
    "... lots more items"
  ],
  "bits": [
    "000100000110000010100000001100000001000010100101010101011100000000000000",
    "100001010010101010101110000000000000000010000011000001010000000110000000",
    "... lots more items"
  ],
}

```

The `reserved` key is not initially present, but is set to true when the job is reserved
for processing.

## Step 1: setting up HPC environment.

Install conda using miniforge, 
then set up a new environment (this can be slow):

```bash
bash  # make sure we're using bash.
conda create --name genra python=3.11
conda activate genra
pip install -r requirements.pip.txt  # from top level of genra_app repo.
```

## Step 2: running jobs.

`fast_jaccard.py` will record log messages in the collection using:

    python fast_jaccard.py log Start processing

Omit the message to see the current log:

    Metadata log messages:
    Mon May  1 19:26:16 2023 This collection created
    Mon May  1 21:01:39 2023 Start processing

Edit `product.sh` to specify the FPs and filters you want to generate.
`product.sh` schedules jobs which are the cross product of the set of
FPs and filters you specify.

## Step 3: monitoring progress.

### Monitoring from the HPC end.

View your running jobs:

```sh
squeue | grep tbrown02 | cat -n  # or whatever your username is.
    1 5472470       ord genra_ja tbrown02  R    2:04:35      1 r2n33
    2 5472458       ord genra_ja tbrown02  R    2:04:45      1 r2n32
    ...
```

If you need to kill jobs,

    scancel 5472470 5472458 ....

See the latest output for running jobs:

    ls -t | head | xargs tail -n 3 -f

Most of the time this will show a lot of text like this:

```
==> genra_jaccard.o5472335 <==
0.288078 per sec.
0.285182 per sec.
```

although you'll also see mongo connection renewal messages and ignorable mongo
related warnings.  When jobs are first starting the top of the output will look
like this:

```
Fri Apr 28 13:30:32 EDT 2023
0428-133035:genra_celery.py:23 Using Celery broker: None
0428-133035:db_connection.py:80 mongodb://user:pword@...
0428-133035:db_connection.py:226 Connect '' OK: URI connector
0428-133035:db_connection.py:80 mongodb://user:pword@...
Wanted 186 blocks, got 186
Building array.
1629 blocks to load.
Loading block 1609
1628053 chems., 2048 bits.
```

The `Loading block` line overwrites itself, use `less -r` to view the file with intended layout.

### Monitoring from the mongodb end.

Count chemicals and batches / jobs done:
```mongosh
genra> db.fj_chm_httr.countDocuments({chem_id: {$exists:1}})
830850

genra> db.fj_chm_httr.countDocuments({done: true})
688
```

As the code runs it creates documents in the collection with a `chem_id` key:

```mongosh
genra> db.fj_chm_httr.findOne({chem_id: {$exists:1}})
{
  _id: ObjectId("644be6ae1f4da2f455c60064"),
  chem_id: 'DTXCID001000007',
  nn: [
    'DTXCID001000007', 'DTXSID50442193',  'DTXCID701226987', 'DTXSID90545718',
    'DTXCID50920825',  'DTXSID20805438',  'DTXCID30921693',  'DTXCID50970209',
    ...
  ],
  sims: [
    1,                   1,                   0.5833333134651184,
    0.47826087474823,    0.47826087474823,    0.47826087474823,
    ...
  ]
}
```

You can check these against known results to see if the code is working correctly.

### Re-queueing failed jobs.

```mongosh
genra> db.fj_chm_httr.updateMany({done: false, reserved:true}, {$unset:{reserved: 1}})
```

## Step 4: Loading results in `fp_info`.

The `fp_info` collection is used to store information about fingerprints.
Run `fast_jaccard.py load <collection_name>` to load the results of the HPC jobs
into `fp_info`.

## Step 5: Ensure indexes are present.

See the [main README](../../../../README.md) for notes on running `flask
commands index create` to add any missing indexes.
