"""This module has some settings for the comparison."""
import datetime


class Identifier:
    """
    A class that keeps track of identifier information. Usually identifier
    may be DTXCID, but this is abstracted in the comparison so that
    collections with DTXCID missing (like PB_V5 toxcast_fp collection) can
    still be compared, with something like DTXSID (or in the future other
    fields like casrn).
    """

    def __init__(self, id_name, id_field):
        self.id_name = id_name
        self.id_field = id_field


# 804: add fields
"""`comparison_settings` is a list of comparisons to be made - each object
corresponds to a comparison. When adding or modifying, carefully note
which fields are present in examples and be sure that they're all defined."""
comparisons_settings = [
    {
        "fp_name": "chm_mrgn_AND_chm_httr",
        "src_db_suffix": "PB_V5",
        "src_col_name": "chms_fp",
        "src_fps": ["mrgn.ds", "httr.ds"],
        "dst_db_suffix": "CCTE_PROD",
        "dst_col_name": "chms_fp",
        "fps": ["mrgn.ds", "httr.ds"],
        "required_fields": ["dsstox_cid", "mol_weight", "httr", "mrgn", "name"],
        "desired_fields": ["dsstox_sid", "casrn"],
        "identifier_class": Identifier("cid", "dsstox_cid"),
        "label": f"{str(datetime.date.today())}_old_db_against_ccte_prod",
    },
    {
        "fp_name": "chm_ct",
        "src_db_suffix": "PB_V1",
        "src_col_name": "chemotypes",
        "src_fps": ["chemotypes.ds"],
        "dst_db_suffix": "CCTE_PROD",
        "dst_col_name": "chemotypes_calc",
        "fps": ["chemotypes.ds"],
        "required_fields": [
            "dsstox_cid",
            "mol_weight",
            "chemotypes",
            "name",
        ],
        "desired_fields": ["dsstox_sid"],
        "identifier_class": Identifier("cid", "dsstox_cid"),
        "label": f"{str(datetime.date.today())}_old_db_against_ccte_prod",
    },
    {
        "fp_name": "bio_txct",
        "src_db_suffix": "PB_V5",
        "src_col_name": "toxcast_fp",
        "src_fps": ["bio1.ds"],
        "dst_db_suffix": "CCTE_PROD",
        "dst_col_name": "toxcast_fp",
        "fps": ["fpnd.all.ds"],
        "required_fields": [
            "dsstox_cid",
            "fpnd",
            "name",
            "mol_weight",
        ],
        "desired_fields": ["dsstox_sid", "src"],
        "identifier_class": Identifier("sid", "dsstox_sid"),
        "label": f"{str(datetime.date.today())}_old_db_against_ccte_prod",
    },
    {
        "fp_name": "tox_txrf",
        "src_db_suffix": "PB_V1",
        "src_col_name": "tox5_fp",
        "src_fps": ["tox_fpp1.ds"],
        "dst_db_suffix": "CCTE_PROD",
        "dst_col_name": "toxref_tr_fp",
        "fps": ["tox_fp2.fp_pos.ds"],
        "required_fields": [
            "dsstox_cid",
            "mol_weight",
            "name",
            "src",
        ],
        "desired_fields": ["dsstox_sid", "chemical_casrn"],
        "identifier_class": Identifier("cid", "dsstox_cid"),
        "label": f"{str(datetime.date.today())}_old_db_against_ccte_prod",
    },
]
