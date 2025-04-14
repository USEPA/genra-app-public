import io

import cairo
from rdkit import Chem
from rdkit.Chem.Draw import cairoCanvas


def smiles2svg(smiles, size=(100, 100)):
    """Originally from genra-analysis/lib/db/vis.py"""

    if smiles == "FAIL" or smiles is None:
        return ""
    imageData = io.BytesIO()
    surf = cairo.SVGSurface(imageData, size[0], size[1])
    mol = Chem.MolFromSmiles(smiles)
    if mol is None:
        return ""
    mol = Chem.Mol(mol.ToBinary())
    Chem.Kekulize(mol)
    Chem.SanitizeMol(
        mol,
        sanitizeOps=Chem.SanitizeFlags.SANITIZE_ALL
        ^ Chem.SanitizeFlags.SANITIZE_KEKULIZE
        ^ Chem.SanitizeFlags.SANITIZE_SETAROMATICITY,
    )
    ctx = cairo.Context(surf)
    canv = cairoCanvas.Canvas(ctx=ctx, size=size, imageType="svg")
    Chem.Draw.MolToImage(mol, size=size, canvas=canv)
    canv.flush()
    surf.finish()
    return imageData.getvalue()
