"""Union of pesticide lists from input Excel files."""

from pathlib import Path

import pandas as pd

from genraweb.resources import DB

DB.pesticideRAC.drop()
for path in Path(__file__).parent.glob("*.xlsx"):
    df = pd.read_excel(path, sheet_name="UseMe")
    for row in df.itertuples():
        if isinstance(row.DSSTox_Substance_Id, str):
            DB.pesticideRAC.insert_one(
                row._asdict() | {"dsstox_sid": row.DSSTox_Substance_Id}
            )
