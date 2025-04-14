"""Functions to manage multi-chemical targets, i.e.  chem_id=id0,id1,id2.

From product owner discussion:

    For chems. A,B,C,D,E, predict missing data from A,B,C,D,E

    relies on being able to pass DTXCID123,DTXCID234,DTXCID345 around as a "chem_id"
    panel 4 would have predictions for all columns
    hover over display is ~ok
    sorting - limit to name / observations
    sorting - possible add most / least impacted - pos/neg predictions
    but could add column ordering on mol. mass or sim.
    download would be wider with repeated columns
    fix "role" designation, no pairwise similarity
"""
from genraweb.lib.chem_id import ChemID
from genraweb.lib.fp.fpclass import FPGen


def clean_id(chem_id: str) -> str:
    """Promote and de-duplicate IDs in 'id0,id1,id2'."""
    ids = {}  # use dict to maintain order
    for chem_id in chem_id.split(","):  # drop dupes in input
        ids[chem_id.strip()] = 1
    promoted = {}
    for chem_id, _ in map(ChemID.promote_id, ids):
        if ChemID.id_type(chem_id) != ChemID.NAME:
            promoted[chem_id] = 1
    return ",".join(promoted)


def chem_ids(chem_id: str) -> list:
    """Split on commas."""
    return chem_id.split(",")


def is_multi(chem_id: str) -> bool:
    """Check for commas."""
    return "," in chem_id


def neighbors(chem_id: str) -> list:
    """'Fake' neighbors for multitarget."""
    neighbors = []
    for one_chem in chem_ids(chem_id):
        _, chem = ChemID.promote_id(one_chem)
        if chem:
            chem["chem_id"] = one_chem
            chem["similarity"] = 1.0
            # Some code refers to foo["fpds_mrgn"] etc., dummy entry for that.
            chem["fpds_multitarget"] = ["A", "B", "C"]
            chem["fpds_user-defined"] = ["A", "B", "C"]
            for fp_id in FPGen.FPClass:  # fake for all FPs
                chem[f"fpds_{fp_id}"] = ["A", "B", "C"]
            neighbors.append(chem)
    return neighbors


def _rotate_aggregator(aggregator):
    """Move column 0 to the end of the table."""
    aggregator.frame.col_def = aggregator.frame.col_def[1:] + [
        aggregator.frame.col_def[0]
    ]
    for row_i in aggregator.frame.row:
        row_i[:] = row_i[1:] + [row_i[0]]
    chems = chem_ids(aggregator.state.chem_id)
    chems[:] = chems[1:] + [chems[0]]
    aggregator.state.chem_id = ",".join(chems)


def permute(aggregator, predictor, first_only=False):
    """Run predictor on each column."""
    # To delete any sorts added by predictor
    sort_count = len(aggregator.sort_options)

    multi_chem_id = aggregator.state.chem_id
    all_ids = chem_ids(multi_chem_id)
    for col in range(len(all_ids)):
        if aggregator.state.engine != "genrapred":
            aggregator.state.chem_id = all_ids[col]
        predictor()
        if first_only:
            break
        _rotate_aggregator(aggregator)

    # Delete any sorts added by predictor.
    aggregator.sort_options = aggregator.sort_options[:sort_count]
    # Restore multi-chem. ID
    aggregator.state.chem_id = multi_chem_id

    return True
