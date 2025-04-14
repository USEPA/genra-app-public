"""This module handles chemical level comparisons of FP array(s).
Checks what elements have been added and/or removed from the array(s)
in the destination collection (dst_col)."""


class NoFPKeyException(Exception):
    """
    A custom exception class for when there is no FP field(s)
    available in the document being examined
    """

    pass


class ChemicalLevelCheck:
    """
    A class that handles comparison of FP arrays of a chemical, as identified
    by its identifier, by looking at what elements have been added and/or
    removed to the destination collection.

    Work is done by calling the `run()` method, which returns a dictionary
    (JSON-like), which gets fed into chemical comparison information check of
    CollectionLevelCheck.
    """

    def __init__(
        self,
        src_col=None,
        dst_col=None,
        src_fps=None,
        fps=None,
        identifier=None,
        identifier_class=None,
    ):
        """
        Parameters
        ----------
                src_col : Pymongo collection class object
                        source
                src_col : Pymongo collection class object
                        destination
                src_fps : List[str]
                        list of dotted FP keys for src (usually only one item)
                fps : List[str]
                        list of dotted FP keys for dst (usually only one item)
                        usually same as src_fps
                required_fields : List[str]
                        list of name of required fields in each document
                desired_fields : List[str]
                        list of name of desired fields in each document
                identifier_class : Identifier object
                        identifier used to distinguish documents - usually cid or sid
                        see class definition in `settings.py`
                fp_name : str
                        FP shorthand, used for names of saved files
        """
        args_list = [src_col, dst_col, src_fps, fps, identifier, identifier_class]
        if any((arg is None for arg in args_list)):
            raise Exception(
                "At least one of the args to this class was not supplied correctly."
            )

        self.src_col = src_col
        self.dst_col = dst_col
        self.src_fps = src_fps
        self.fps = fps
        self.identifier = identifier
        self.identifier_class = identifier_class

    def navigate_doc(self, doc, dotted_key):
        """iterates through dictionary keys to get FP array, and returns it"""
        keys = dotted_key.split(".")
        component = doc
        for key in keys:
            if key not in component:
                # TODO: would be ideal to include which colleciton this refers
                raise NoFPKeyException(
                    "Could not find relevant key in document for "
                    f"{self.identifier} and the given dotted_key {dotted_key} "
                )
            component = component[key]
        return component

    def return_fp_comparison_info(self, src_ds, dst_ds):
        src_ds_set, dst_ds_set = set(src_ds), set(dst_ds)
        return {
            "added": list(dst_ds_set - src_ds_set),
            "removed": list(src_ds_set - dst_ds_set),
        }

    def compare_fps(self, src_doc, dst_doc):
        info = {}
        for src_fp, fp in zip(self.src_fps, self.fps):
            try:
                src_ds, dst_ds = self.navigate_doc(src_doc, src_fp), self.navigate_doc(
                    dst_doc, fp
                )
                fp_info = self.return_fp_comparison_info(src_ds, dst_ds)
            except NoFPKeyException as e:
                fp_info = e
            # uses the FP name from dst_col as key
            info.update({fp: fp_info})
        return info

    def run(self):

        id_field = self.identifier_class.id_field

        src_doc = self.src_col.find_one(
            {id_field: self.identifier}, {fp: 1 for fp in self.src_fps}
        )

        dst_doc = self.dst_col.find_one(
            {id_field: self.identifier}, {fp: 1 for fp in self.fps}
        )

        return self.compare_fps(src_doc, dst_doc)
