"""This module handles collection level comparisons. Two collections,
source collection and destination collection (denoted src_col and
dst_col respectively) are compared, and this class gets 3 sections of
information in this regard, namely:
- "meta information" : e.g., how many more/less chemicals
- "fields error information" : e.g., how many/which documents in
dst_col have missing values for various fields of interest
- "chemicals comparison info" : e.g., which items in FP array(s) are
added/removed for a given chemical common to both src_col and dst_col

More sections can be added - by adding it to the info object under a
section name, and then making corresponding addition to ReportGenerator."""

import datetime
import random
from multiprocessing.dummy import Pool as ThreadPool

from chemical_level import ChemicalLevelCheck


def run_with_time_printed(function):
    def wrapper_run_with_time_printed(*args, **kwargs):
        start = datetime.datetime.now()
        return_value = function(*args, **kwargs)
        end = datetime.datetime.now()
        print(f"Took {end-start} to run {function.__name__}", flush=True)
        return return_value

    return wrapper_run_with_time_printed


class CollectionLevelCheck:
    """
    A class that handles comparison of two collections, source and destination:
    - source (denoted `src`) refers to ~'expected' data or reference data
    - destination (denoted `dst`) refers to ~`got` data or data we're checking

    Work is done by calling the `run()` method. Compiles information into a
    dictionary object (that is JSON-like), inside an object field `info`. This
    gets fed into ReportGenerator for human-readable consumption.
    """

    def __init__(
        self,
        src_col=None,
        dst_col=None,
        src_fps=None,
        fps=None,
        required_fields=None,
        desired_fields=None,
        identifier_class=None,
        fp_name=None,
    ):
        """
        Parameters
        ----------
                src_col : Pymongo collection class object
                        source
                dst_col : Pymongo collection class object
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

        args_list = [
            src_col,
            dst_col,
            src_fps,
            fps,
            required_fields,
            desired_fields,
            identifier_class,
            fp_name,
        ]
        if any((arg is None for arg in args_list)):
            raise Exception(
                "At least one of the args to this class was not supplied correctly."
            )

        self.src_col_count = src_col.count()
        self.dst_col_count = dst_col.count()
        if not self.src_col_count or not self.dst_col_count:
            error_info_str = f"For {fp_name},"
            if not self.src_col_count:
                error_info_str += " <src>"
            if not self.dst_col_count:
                error_info_str += " <dst>"
            raise Exception(
                f"{error_info_str} collection(s) is(are) empty, check that the "
                "correct collections information is entered in `settings.py`."
            )
        self.src_col, self.dst_col = src_col, dst_col

        self.src_fps = src_fps
        self.fps = fps
        self.required_fields = required_fields
        self.desired_fields = desired_fields
        self.identifier_class = identifier_class
        self.fp_name = fp_name

        # set up blank template for the info object
        self.info = {
            "meta_info": {},
            "fields_error_info": {},
            "chemicals_comparison_subset_info": {},  # FIXME: make non-subset
            "runtime_info": {},
        }

    def find_duplicate_identifiers(self, col):
        id_field = self.identifier_class.id_field
        query_find_duplicate_identifiers = [
            {"$group": {"_id": f"${id_field}", "count": {"$sum": 1}}},
            {"$match": {"_id": {"$ne": None}, "count": {"$gt": 1}}},
            {"$project": {id_field: "$_id", "count": "$count", "_id": 0}},
        ]
        cursor_duplicate_identifiers = col.aggregate(
            query_find_duplicate_identifiers, allowDiskUse=True
        )
        return list(cursor_duplicate_identifiers)

    def find_unique_identifiers(self, col):
        id_field = self.identifier_class.id_field
        query_find_all_identifiers = (
            {id_field: {"$exists": True}},
            {id_field: 1, "_id": False},
        )
        cursor_all_identifiers = col.find(*query_find_all_identifiers)
        all_identifiers_generator = (res[id_field] for res in cursor_all_identifiers)
        return set(all_identifiers_generator)

    def threaded_map(self, function, input_list, num_threads):
        """from https://stackoverflow.com/a/28463266
        basically the standard python map function, but applies it in
        multithreaded manner; used to minimize DB IO costs"""
        pool = ThreadPool(num_threads)
        results = pool.map(function, input_list)
        pool.close()
        return results

    @run_with_time_printed
    def get_meta_info(self):

        id_name = self.identifier_class.id_name

        def query_identifier_info(col):
            return {
                f"{id_name}s_duplicate": self.find_duplicate_identifiers(col),
                f"{id_name}s_unique": self.find_unique_identifiers(col),
            }

        col_types = [self.src_col, self.dst_col]
        results = self.threaded_map(query_identifier_info, col_types, 2)

        # extract duplicate identifier information
        src_duplicate_identifiers = results[0][f"{id_name}s_duplicate"]
        dst_duplicate_identifiers = results[1][f"{id_name}s_duplicate"]

        # extract identifier change information
        src_identifiers_set = results[0][f"{id_name}s_unique"]
        dst_identifiers_set = results[1][f"{id_name}s_unique"]
        identifiers_common = list(src_identifiers_set & dst_identifiers_set)
        identifiers_added = list(dst_identifiers_set - src_identifiers_set)
        identifiers_removed = list(src_identifiers_set - dst_identifiers_set)

        self.info["meta_info"].update(
            {
                "num_documents_in_src": self.src_col_count,
                "num_documents_in_src_desc": (
                    "Number of documents in source collection"
                ),
                "num_documents_in_dst": self.dst_col_count,
                "num_documents_in_dst_desc": (
                    "Number of documents in destination collection"
                ),
                f"num_{id_name}s_added_in_dst": len(identifiers_added),
                f"num_{id_name}s_added_in_dst_desc": (
                    f"Number of distinct {id_name}s added in destination collection"
                    " from source collection"
                ),
                f"num_{id_name}s_removed_in_dst": len(identifiers_removed),
                f"num_{id_name}s_removed_in_dst_desc": (
                    f"Number of distinct {id_name}s removed in destination collection"
                    " from source collection"
                ),
                f"num_{id_name}s_common": len(identifiers_common),
                f"num_{id_name}s_common_desc": (
                    f"Number of distinct {id_name}s in common between"
                    " source and destination collections"
                ),
                f"{id_name}s_duplicate_in_src": src_duplicate_identifiers,
                f"{id_name}s_duplicate_in_src_desc": (
                    f"List of {id_name}s of documents with duplicate {id_name}s in"
                    " source collection, including duplication count"
                ),
                f"{id_name}s_duplicate_in_dst": dst_duplicate_identifiers,
                f"{id_name}s_duplicate_in_dst_desc": (
                    f"List of {id_name}s of documents with duplicate {id_name}s in"
                    " destination collection, including duplication count"
                ),
                f"{id_name}s_added_in_dst": identifiers_added,
                f"{id_name}s_added_in_dst_desc": (
                    f"List of distinct {id_name}s added in destination collection"
                    " from source collection"
                ),
                f"{id_name}s_removed_in_dst": identifiers_removed,
                f"{id_name}s_removed_in_dst_desc": (
                    f"List of distinct {id_name}s removed in destination collection"
                    " from source collection"
                ),
                f"{id_name}s_common": identifiers_common,
                f"{id_name}s_common_desc": (
                    f"List of distinct {id_name}s in common between"
                    " source and destination collections"
                ),
            }
        )

    @run_with_time_printed
    def get_dst_collection_fields_error_info(self):

        fields = list(set(self.required_fields + self.desired_fields))

        id_field = self.identifier_class.id_field

        # we could be extracting
        query_docs_with_fields_error = (
            {"$or": [{field: None} for field in fields]},
            {field: 1 for field in fields},
        )

        cursor_docs_with_fields_error = self.dst_col.find(*query_docs_with_fields_error)

        field_error_template = {
            "missing_count": 0,
            "missing_list": [],
            "null_count": 0,
            "null_list": [],
        }

        fields_error_info = {field: field_error_template.copy() for field in fields}
        for document in cursor_docs_with_fields_error:
            if id_field not in document:
                # case where there's no identifier, unsure if applicable right now
                continue
            identifier = document[id_field]
            for field in fields:
                if field not in document:
                    error_type = "missing"
                elif document[field] is None:
                    error_type = "null"
                else:
                    continue
                error_count_key = error_type + "_count"
                error_list_key = error_type + "_list"
                fields_error_info[field][error_count_key] += 1
                fields_error_info[field][error_list_key].append(identifier)
        self.info["fields_error_info"].update(fields_error_info)

    @run_with_time_printed
    def get_chemicals_comparison_info(self):

        num_threads = 25

        id_name = self.identifier_class.id_name

        if f"{id_name}s_common" not in self.info["meta_info"]:
            self.get_meta_info()

        def compare_chemical(identifier):
            chemical_level_check = ChemicalLevelCheck(
                src_col=self.src_col,
                dst_col=self.dst_col,
                src_fps=self.src_fps,
                fps=self.fps,
                identifier=identifier,
                identifier_class=self.identifier_class,
            )

            return {identifier: chemical_level_check.run()}

        # FIXME: eventually make this non-subset
        common = self.info["meta_info"][f"{id_name}s_common"]
        identifiers_to_look_at = random.sample(common, min(len(common), 1000))
        chemicals_comparison_info_list = self.threaded_map(
            compare_chemical, identifiers_to_look_at, num_threads
        )

        # convert this to a dictionary
        chemicals_comparison_info = {}
        for info in chemicals_comparison_info_list:
            chemicals_comparison_info.update(info)

        # FIXME: change key after making non-subset
        self.info["chemicals_comparison_subset_info"].update(chemicals_comparison_info)

    def run(self):
        """As more get_<info_type>_info() methods are added to this class, add them here
        and corresponding reporting methods in ReportGenerator"""

        start = datetime.datetime.now()
        self.get_meta_info()
        meta_time = datetime.datetime.now() - start

        start = datetime.datetime.now()
        self.get_dst_collection_fields_error_info()
        collection_fields_error_time = datetime.datetime.now() - start

        start = datetime.datetime.now()
        self.get_chemicals_comparison_info()
        chemicals_comparison_time = datetime.datetime.now() - start

        self.info.update(
            {
                "runtime_info": {
                    "meta_time": meta_time,
                    "collection_fields_error_time": collection_fields_error_time,
                    "chemical_comparison_subset_time": chemicals_comparison_time,
                }
            }
        )
