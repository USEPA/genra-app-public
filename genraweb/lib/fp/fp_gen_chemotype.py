import csv
import subprocess
import tempfile
from itertools import compress
from pathlib import Path

from lxml import etree

CORINA = "/opt/CORINA_Symphony/CORINA_Symphony_14698/bin/moses"
CORINA_CMD = [
    CORINA,
    "-N",
    "symphony",
    "batch",
    "-i",
    "compounds.smi",
    "-o",
    "results.txt",
    "descriptors",
    "-f",
    "<CORINA_XML>",
]


def preferred_id(chem):
    """Pick preferred id from dict

    Args:
        chem (dict): chem. info.

    Returns:
        str: CID if present else SID if present else SMILES
    """
    return chem.get("dsstox_cid") or chem.get("dsstox_sid") or chem["smiles"]


def get_csrml_names(toxprint, prepend_subgraph_id=False):
    """Used to pull "characteristics" (names of bits) from header of Corina semi-colon
    separated output, but AIM FP input XML has \u2010 Unicode hyphens rather than ASCII
    dashes and Corina is replacing them with spaces so:
    """
    dom = etree.parse(open(toxprint))
    namespace = "http://www.molecular-networks.com/schema/csrml"
    bits = dom.xpath("//ns:subgraph", namespaces={"ns": namespace})
    names = []
    for bit in bits:
        name = bit.xpath(".//ns:label/text()", namespaces={"ns": namespace})[0]
        name = (
            name.strip('"')
            .replace("\u2010", "-")
            .replace("\n", " ")
            .replace("  ", " ")
            .strip()
        )
        if prepend_subgraph_id:  # Labels are not unique
            name = bit.get("id") + ": " + name
        names.append(name)

    return names


def run_corina(chem_ids, toxprint_file, prepend_subgraph_id=False):
    """Run Corina for the listed ids.

    Args:
        chem_ids (list(dict)): ids of chemicals needing fingerprints, like
            [{'dsstox_sid': 'DSSTOXSID2363', 'smiles': 'CCC'},
             {'dsstox_cid': 'DSSTOXCID4471', 'smiles': 'CCCO'},
             {'smiles': 'CCOCO'},
            ]
        will use CID, then SID, then smiles, as ID for chem.  Only smiles is
        required.

    Returns:
        mapping: Fingerprints
    """

    # drop things with no smiles
    chem_ids = [i for i in chem_ids if (i.get("smiles") or "").strip()]
    if not chem_ids:
        return {}

    toxprint = Path(__file__).with_name(toxprint_file)
    names = get_csrml_names(toxprint, prepend_subgraph_id)
    with tempfile.TemporaryDirectory() as tmpdir:
        tmpdir = Path(tmpdir)
        # copy in the toxprint data
        (tmpdir / toxprint_file).write_bytes(toxprint.read_bytes())
        # create list of "<smiles>\t<chem_id>" entries
        with (tmpdir / "compounds.smi").open("w") as out:
            for chem in chem_ids:
                # pick ID; CID > SID > smiles
                id_ = (preferred_id(chem)).strip()
                out.write(f"{chem['smiles'].strip()}\t{id_}\n")
        # run Corina, seems to take ~5 seconds for 3 (i.e. ~1) chem
        corina_cmd = [toxprint_file if i == "<CORINA_XML>" else i for i in CORINA_CMD]
        subprocess.run(
            corina_cmd, cwd=tmpdir, capture_output=True, timeout=3600
        ).check_returncode()
        # results.txt is ';' separated rows of
        # <our_id>;0;0;0;1;1;0;1;0;<junk>;<status>
        # with the first row, the column headings, being the names of the
        # characteristics corresponding to the 0s and 1s
        with (tmpdir / "results.txt").open() as result:
            reader = csv.reader(result, delimiter=";")
            # get the list of characteristics evaluated from the first line
            # Ignoring characteristics, see comments for `bits` above
            # characteristics = next(reader)[1:-2]
            next(reader)  # Skip first line
            fps = {("characteristics", None): names}
            # map our IDs to lists of the selected (1 not 0) characteristics
            # id from Corina is sometimes '|^1:0 2| DTXCID10740506', take the last part
            for result in reader:
                key = result[0].split()[-1]
                if result[-1] != "No errors":
                    fps[("fail", key)] = result
                    continue
                fps[key] = list(compress(names, map(int, result[1:-2])))
                fps[("bs", key)] = "".join(result[1:-2])

    return fps
