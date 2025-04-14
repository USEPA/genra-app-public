"""Aggregator for ToxCast data."""
from collections import defaultdict
from itertools import chain

import numpy as np
import pandas as pd
from genra.rax.skl.cls import GenRAPredClass
from genra.rax.skl.reg import GenRAPredValue

from genraweb.deploy_types import DeployType
from genraweb.lib.chem_id import ChemID
from genraweb.lib.engine.engines import PredEngine
from genraweb.lib.fp.fpclass import FPToxcast
from genraweb.lib.fp.genfputils import FPGen
from genraweb.lib.genrapred import runGenRA
from genraweb.lib.logging import logger
from genraweb.lib.properties.physprop import prop_data
from genraweb.resources import DB, ENDPOINT_DETAILS_TOXCAST, MESSAGE

from .aggregator import Aggregator, AGGridMixin, BinaryMixin


# class ToxCastAgg(Aggregator):
class ToxCastAgg(BinaryMixin, AGGridMixin, Aggregator):
    """Aggregator for ToxCast binary data."""

    # Aggregator attributes
    agg_id = "bio_txct"
    name = "ToxCast"
    description = "The ToxCast DB"
    groupings = {
        "bio_fp": {"name": "ToxCast Fingerprint", "description": "A ToxCast FP"}
    }
    maxDepType = DeployType.PROD
    agg_fp_class = FPGen.FPClass["bio_txct"]
    fp_y_pos = "biop_txct"
    fp_y_neg = "bion_txct"
    label_path = "hits"

    def get_row_label(self, ac_name):
        """Get the corresponding "assay_component_name_desc" field.

        Parameters
        ----------
        ac_name : str
            assay component name

        Returns
        ----------
        label : str
            assay_component_name_desc field, or just `ac_name` if DNE

        """
        if hit := ENDPOINT_DETAILS_TOXCAST.get(ac_name):
            label = hit.get("assay_component_desc", ac_name)
        else:
            label = ac_name

        return label

    def get_positive_label(self, ac_name, hits_df):
        """
        ac_name : assay component name
        hits : "hits" data in collection that stores endpoint level data
        """
        # Per discussion with PO, currently there isn't a sensible positive label to attach.
        # Below code attaches AC10 and AC50 vals
        #
        # label_df = pd.DataFrame(hits)
        # label_df = label_df[label_df.assay_component_name == ac_name]
        # ac10, ga = "", ""
        # if "modl_ga" in label_df.columns:
        #     label_df = label_df[label_df.modl_ga == label_df.modl_ga.max()]
        #     if label_df.empty:
        #         return None
        #     ga = round(label_df.modl_ga.iat[0], 3)
        # if "modl_ac10" in label_df.columns:
        #     ac10 = round(label_df.modl_ac10.iat[0], 3)

        # return f"AC10={ac10}, Gain AC50={ga}"

        return {"text": "hit"}
