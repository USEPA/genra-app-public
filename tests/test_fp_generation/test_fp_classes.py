import pytest

from genraweb.lib.fp.fpclass import FPGen
from genraweb.lib.fp.genfputils import get_ds_order

CHEM_FPS = [i for i in FPGen.FPClass if i.startswith("chm_")]


def test_fp_classes():
    """Check that all registered FP classes are in the preferred order list and
    visa versa.
    """
    extra = set(FPGen.FPClass) - set(FPGen._FPClasses)
    missing = set(FPGen._FPClasses) - set(FPGen.FPClass)
    assert not extra, f"FP classes not in FPGen._FPClasses: {extra}"
    assert not missing, f"FP classes in FPGen._FPClasses not registered: {missing}"


def test_fp_registration():
    """test FP registration"""

    class FPnew(FPGen):  # noqa
        description = "Description of new fp"
        fp_id = "new_fp"
        fp_coll_name = "new_fp_collection_name"

    assert FPGen.FPClass.get("new_fp") == FPnew
    del FPGen.FPClass["new_fp"]


@pytest.mark.parametrize("fp_id", FPGen.FPClass)
def test_fp_bit_names_gt10(fp_id):
    """Are bit_names() for all FP as expected?"""
    assert (
        (bits := len(FPGen.FPClass[fp_id].bit_names())) > 10
        or fp_id == "chm_phch"
        and bits == 4
    )


@pytest.mark.parametrize("fp_id", CHEM_FPS)
def test_fp_bit_names_match(fp_id):
    """Are calculated bit_names() close to slower looked up values?"""
    fp = FPGen.FPClass[fp_id]
    # Assumes 80% of possible answers seen in data.
    if fp_id == "chm_phch":
        assert len(fp.bit_names()) == 4
        return
    assert (
        1
        <= (
            len(fp.bit_names())
            / len(get_ds_order(fp, fp.fp_fields[0].collection, fp.fp_fields[0].path))
        )
        <= 1.2
    )


@pytest.mark.parametrize("fp_id", CHEM_FPS)
def test_fp_counts(fp_id):
    """Are counts for chem. FP as expected?"""
    from genraweb.resources import DB

    fp = FPGen.FPClass[fp_id](DB, FPGen.FPClass[fp_id].fp_output_basename)
    possible = sum(1 for i in fp.all_chem_ids())
    existing = fp.DB[fp.fp_output_basename].count_documents(
        {"dsstox_cid": {"$ne": None}}
    )
    assert possible == existing
