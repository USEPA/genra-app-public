import re
import urllib
from pathlib import Path

from flask import make_response
from flask_openapi3 import APIBlueprint
from pymongo.errors import OperationFailure

from genraweb.lib.chem_id import ChemID
from genraweb.lib.logging import logger
from genraweb.lib.svg import smiles2svg
from genraweb.resources import DB, UI_URL_PREFIX
from genraweb.routes.api_models import ViewChemPath

viewChem_bp = APIBlueprint("viewChem_bp", __name__)

NO_SVG = Path(__file__).with_name("noimage.svg").read_text()


def maybe_decode(dat):
    """dat.decode("utf8") if bytes else dat"""
    return dat.decode("utf8") if isinstance(dat, bytes) else dat


@viewChem_bp.get(
    urllib.parse.urljoin(UI_URL_PREFIX, "viewChem/<path:chem_id>.svg"),
    responses={200: {"description": "An SVG rendering of the chemical"}}
)
def viewChemSvg(path: ViewChemPath):
    """View the input chemical in svg format
    ---
    tags:
      - UI_support_v3
      - UI_support_v4
    parameters:
      - name: chem_id
        required: true
        in: path
        schema:
          $ref: "#/components/schemas/chem_id"
    responses:
      200:
        description: An SVG rendering of the chemical
    """
    # Possibly because mongo can store string or blobs and the DB may have either in it
    # from previous actions, it's hard to be clear whether we're dealing with str or
    # bytes at all times, so just wrap in maybe_decode()

    # check in the MongoDB cache collection
    chem_id = path.chem_id
    C = DB.svg.find_one(dict(chem_id=chem_id), {"svg": 1})

    if C is not None:  # in mongo cache
        svg = C["svg"]
    else:
        promoted, chem = ChemID.promote_id(chem_id)
        if chem_id != promoted:
            logger.info("viewChem promoted %s to %s", chem_id, promoted)
        if chem and chem.get("smiles"):
            smiles = chem["smiles"]
        elif ChemID.id_type(promoted) == ChemID.SMILES:
            smiles = promoted
        else:
            smiles = None
            svg = ""

        if smiles:
            svg = smiles2svg(smiles)
            if svg.strip():
                try:
                    DB.svg.insert_one(dict(chem_id=promoted, smiles=smiles, svg=svg))
                except OperationFailure:  # ok if we can't cache in DB
                    pass

    if not svg.strip():
        svg = NO_SVG

    # Checking here rather than smiles2svg to filter out bad images already in DB.
    # Red square is red and had 3 sides.  4 sides, but last ends in Z, not L. Bonds are
    # single strokes, so below seems sufficient.
    red_squares = re.search(
        r"rgb\(100%,0%,0%\).*M(\s[-0-9.]+\s[-0-9.]+\sL){3}", maybe_decode(svg)
    )
    if red_squares:
        svg = NO_SVG

    response = make_response(svg)
    response.content_type = "image/svg+xml"
    return response
