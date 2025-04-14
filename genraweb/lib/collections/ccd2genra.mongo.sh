db.ccd_chem_details.aggregate(
    [
        // {"$match": {"name": "Bisphenol A"}},
        // {"$limit": 22},
        {
            "$project": {
                "name": "$preferredName",
                "dsstox_sid": "$dtxsid",
                "dsstox_cid": "$dtxcid",
                "mol_formula": "$molFormula",
                "mol_weight": "$averageMass",
                "monoisotopic_mass": "$monoisotopicMass",
                "smiles": "$smiles",
                "is_markush": "$isMarkush",
                "casrn": "$casrn",
                "inchi_key": "$inchikey",
                "iupac": "$iupacName",
                "synonyms": "$synonyms",
            }
        },
        {"$out": "draft_compounds"},
    ]
)
