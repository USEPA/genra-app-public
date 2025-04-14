import json
import os
import pdb
import random
import urllib

import pathlib2


def _open(full_json_path):
    data = None
    with open(full_json_path, "r") as f:
        data = json.load(f)
    if not data:
        raise Exception("Could not read in " + full_json_path)
    return data


class SetUp:
    """
    This is a helper class that reads in `controls.json` and prepares test 'items' for pytest use.

    The `run()` method reads in test data (i.e., expected data) and eventually returns two objects:

    `items`: a list of test `item`, each of which has id, dtxcid, endpoint, data  (key: 'id', 'chemical', 'endpoint', 'data' respective).

    `ids`: a list of string (id) for each corresponding test `item`. Ordering here corresponds with that of `items`.
    """

    def __init__(self, controls_full_fnamne="controls.json"):
        """
        controls_full_name should be the full path
        """
        self.controls = _open(controls_full_fnamne)

    def _get(self, key):
        return self.controls[key].get("value")

    def filter(self, filter_type, default=[]):
        selected = self._get("SELECTED_" + filter_type)

        if not selected:
            selected = []

            if filter_type == "ENDPOINTS":
                for default_key in self._get("DEFAULT_ENDPOINTS"):
                    selected += self._get(default_key)

            elif filter_type == "FILES":
                selected = [
                    fname
                    for fname in list(os.listdir(self.data_dir))
                    if fname.endswith(".json")
                ]

            elif filter_type == "CHEMICALS" and default:
                selected = default

            else:
                pass

        return list(set(selected) - set(self._get("DESELECTED_" + filter_type)))

    def create_test_id(self, test_dict, endpoint):
        return (
            self.data_dir
            + "/"
            + test_dict["file"]
            + "::"
            + test_dict["chemical"]
            + "::"
            + endpoint
        )

    def run(self):
        self.data_dir = self._get("DATA_DIR")
        filtered_files = self.filter("FILES")
        chemicals = []  # DTXCIDs
        test_dict_list = []
        for file in filtered_files:
            with open(os.path.join(self.data_dir, file), "r") as f:
                json_data = json.load(f)

            if not json_data or json_data["genra_error"]:
                continue

            dtxcid = json_data["DTXCID"]
            test_dict = {
                "file": file,
                "chemical": dtxcid,
                "test_data": json_data,
            }
            chemicals.append(dtxcid)
            test_dict_list.append(test_dict)

        filtered_chemicals = self.filter("CHEMICALS", default=chemicals)
        filtered_test_dict_list = [
            test_dict
            for test_dict in test_dict_list
            if test_dict["chemical"] in filtered_chemicals
        ]

        if len(filtered_chemicals) > len(filtered_test_dict_list):
            # some of the 'desired' test data as defined in controls aren't valid (i.e., user is asking to test
            #  chemicals we don't have good data for. Raise an exception in that case.
            just_dtxcid = [
                test_dict["chemical"] for test_dict in filtered_test_dict_list
            ]
            dne_list = [
                dtxcid for dtxcid in filtered_chemicals if dtxcid not in just_dtxcid
            ]
            raise Exception("THE FOLLOWING could not be tested: " + str(dne_list))

        # we now take a random subset if SELECTED_FILES and SELECTED_CHEMICALS aren't defined
        if not self._get("SELECTED_FILES") and not self._get("SELECTED_CHEMICALS"):
            size = self._get("NUM_CHEMICALS")
            if size < len(filtered_test_dict_list):
                filtered_test_dict_list = random.sample(test_dict_list, size)

        filtered_endpoints = self.filter("ENDPOINTS")
        pytest_ids = []
        pytest_items = []
        for test_dict in filtered_test_dict_list:
            for endpoint in filtered_endpoints:
                pytest_id = self.create_test_id(test_dict, endpoint)
                pytest_item = {
                    "id": pytest_id,
                    "chemical": test_dict["chemical"],
                    "endpoint": endpoint,
                    "data": test_dict["test_data"][endpoint],
                }
                pytest_ids.append(pytest_id)
                pytest_items.append(pytest_item)

        return pytest_items, pytest_ids
