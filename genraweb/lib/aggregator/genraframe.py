"""
The GenRA "Dataframe"

Used to represent the GenRA tables from panel 3 onwards.  Mostly used by Aggregator.

Simple Python data structures where column and row headers and cell contents are all
dicts.  .col_def is a list of column definitions (dicts).  .row_def is a list of row
definitions (dicts).  .row is a list (rows) of lists (columns) of dicts (cells).

  .col_def →                [       {name: BPA,               {name: FOOF,
                               similarity: 0.5,          similarity: 0.1,
  .row_def ↓                      chem_id: DTXCID30182},    chem_id: DTXCID0442} ]

                            [  # .row, a list (rows) of lists (cells) of dicts
[                            [
  {name: "CHR: adrenal",      {isPrediction: False,        {isPrediction: False,
   description: Adrenal...            value: 1,                    value: 0,
  },                            observation: no_effect},     observation: no_data},
                             ],
                             [
  {name: "CHR: bone",         {isPrediction: True,         {isPrediction: False,
   description: Bone...               value: 1,                    value: 1,
  },                            observation: 25 mg/kg,       observation: 125 mg/kg},
]                               description: TP; AUC=0;},
                             ],
                            ]

Export to Excel / CSV
=====================

The export code looks for an `_export` element in each col_def to export one or more
columns per frame column.  The _export element is a list like:

    [
        {"name": "Chem. name", "source": ["chem_name", "chem_id"]},
        {"name": "Mass", "source": ["weight"]},
    ]

which will use cell['chem_name'] for the exported "Chem. name" column, if available,
otherwise cell['chem_id'].
"""


class GenraFrame:
    """
    The GenRA "Dataframe"
    """

    def __init__(self):
        self.col_def = []
        self.row_def = []
        self.row = []

    def col_attr(self, attr):
        """Returns a list of values (attr=str) or dicts (attr=[str])."""
        if isinstance(attr, str):
            return [i.get(attr) for i in self.col_def]
        return [{k: i.get(k) for k in attr} for i in self.col_def]

    def row_attr(self, attr):
        """Returns a list of values (attr=str) or dicts (attr=[str])."""
        if isinstance(attr, str):
            return [i.get(attr) for i in self.row_def]
        return [{k: i.get(k) for k in attr} for i in self.row_def]

    def col_index(self, attr):
        """Returns a key -> int mapping."""
        return {i[attr]: n for n, i in enumerate(self.col_def)}

    def row_index(self, attr):
        """Returns a key -> int mapping."""
        return {i[attr]: n for n, i in enumerate(self.row_def)}
