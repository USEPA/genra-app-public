"""This module puts together the pieces to run collections comparisons.
Behavior - what to compare, which fields to focus on, which DB to use, etc. -
is controlled by contents of `settings.py`.

Important: make sure relevant GENRA_DB_* fields are defined in
`.env`, following `template.env`. These will
need to be defined for all DB suffix used in `settings.py`.

Run from the root genra folder inside the API container.
Run with docker-compose up from root folder, with something like:
`conda run -n genra python3 misc/collections_comparison/supervisor.py`
(Note: recommended to run in detached mode to let it run in the background,
as this will take time to complete. However, when run in detached mode it
will be hard to see the errors, if any.)
"""

import datetime
import sys

sys.path.append("/genra")  # needed to access genra.lib.db_connection below

from collection_level import CollectionLevelCheck
from report_generator import ReportGenerator
from settings import comparisons_settings

from genraweb.lib.db_connection import open_mongo_db


def label_maker(label):
    return f"{label}_{str(datetime.date.today())}"


if __name__ == "__main__":

    for setting in comparisons_settings:

        print(f'\n\n<working on {setting["fp_name"]}...>\n')

        src_DB = open_mongo_db(setting["src_db_suffix"])
        dst_DB = open_mongo_db(setting["dst_db_suffix"])
        src_col = src_DB[setting["src_col_name"]]
        dst_col = dst_DB[setting["dst_col_name"]]

        collection_level_check = CollectionLevelCheck(
            src_col=src_col,
            dst_col=dst_col,
            src_fps=setting["src_fps"],
            fps=setting["fps"],
            required_fields=setting["required_fields"],
            desired_fields=setting["desired_fields"],
            identifier_class=setting["identifier_class"],
            fp_name=setting["fp_name"],
        )
        collection_level_check.run()

        report_generator = ReportGenerator(collection_level_check, setting["label"])
        report_generator.run()

        print(f'\n </...finished {setting["fp_name"]}>\n\n')
