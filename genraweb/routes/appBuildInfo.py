"""An endpoint that returns application's build information.
Implemented in ticket GEN-196
"""

import datetime
import os
import pathlib
import subprocess
import sys
import urllib

import pytz
from flask import current_app, json
from flask_openapi3 import APIBlueprint

from genraweb.resources import DB, MISC_URL_PREFIX
from genraweb.routes.api_models import BuildInfo, BuildInfoResponse
from genraweb.routes.api_tags import data_admin_tag

appBuildInfo_bp = APIBlueprint("appBuildInfo_bp", __name__)


def timestamp_to_eastern_str(time_stamp):
    """Given a timestamp, converts it to an equivalent Eastern timezone time
    in a readable string format

    Args:
    ----
        time_stamp (int): Unix timestamp
    """
    time_stamp = int(time_stamp)
    utc_time = datetime.datetime.fromtimestamp(time_stamp, tz=datetime.timezone.utc)
    eastern_time = utc_time.astimezone(pytz.timezone("US/Eastern"))
    return eastern_time.strftime("%a %b %d %H:%M:%S %Z %Y")


def get_most_recent_files(num_files):
    """Returns a list of dictionaries of most recently modified files
    (in full path) and their modification time (readable string in
    local Eastern timezone). Number of files determined by `num_files`.

    Args:
    ----
        num_files (int): Number of most recently modified files to output
    """
    file_paths = list(pathlib.Path().glob("**/*"))

    def is_file_of_interest(posix_path):
        """Given a path, returns a boolean on whether file of interest

        Args:
        ----
            posix_path (Path): File path
        """
        path_str = str(posix_path)
        return all(
            [
                not path_str.startswith("venv_genra_app"),
                not path_str.startswith(".git"),
                "_pycache_" not in path_str,
                ".pyc" not in path_str,
                ".pytest_cache" not in path_str,
            ]
        )

    filtered_file_paths = filter(is_file_of_interest, file_paths)
    file_paths_and_mtimes = [
        (path, os.path.getmtime(path)) for path in filtered_file_paths
    ]
    file_paths_and_mtimes.sort(key=lambda tup: tup[1], reverse=True)
    file_paths_and_mtimes = file_paths_and_mtimes[:num_files]
    results = []
    for path, time_stamp in file_paths_and_mtimes:
        results.append(
            {
                "path": str(path),
                "time_modified": timestamp_to_eastern_str(time_stamp),
            }
        )
    return results


def get_app_build_info(num_files):
    """Returns the dictionary that contains the application build
    information

    Args:
    ----
        num_files (int): Number of most recently modified files to output
    """
    info = {}

    # python version
    info["python_version"] = sys.version

    # mongodb database info
    host, port = DB.client.address
    mongodb_info = {
        "host": host,
        "port": port,
        "database": DB.name,
    }
    try:
        mongodb_info["collections"] = DB.list_collection_names()
    except Exception as err:  # noqa: PLW0703
        mongodb_info["error"] = str(err)
    info["mongodb"] = mongodb_info

    # git
    if pathlib.Path("/genra/.git").is_dir():
        git_command = (
            "git -C /genra log --oneline -n 5 --pretty=format:'%h: %cr, %s'"
            " --abbrev-commit"
        )
        result = subprocess.run(
            git_command,
            shell=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            check=True,
            text=True,
        )
        info["git_log"] = str(result.stdout).splitlines()

    # build time & run time
    types = {
        "time_image_built": "/.dockerbuild",
        "time_app_start": "/.dockerrun",
    }
    for key, fname in types.items():
        with open(os.path.abspath(fname), "r") as file:
            first_line = file.readline().strip()
        time_stamp = datetime.datetime.strptime(
            first_line, "%a %b %d %H:%M:%S %z %Y"
        ).timestamp()
        info[key] = timestamp_to_eastern_str(time_stamp)

    # file changes
    info["recent_files"] = get_most_recent_files(num_files)

    return info


@appBuildInfo_bp.get(
    urllib.parse.urljoin(MISC_URL_PREFIX, "appBuildInfo/"),
    summary=BuildInfo.__doc__,
    tags=[data_admin_tag],
    responses={200: BuildInfoResponse}
)
def appBuildInfo(query: BuildInfo):
    """An endpoint for various app build info - database, python version, etc.
    ---
    tags:
      - Container_Data_Admin
    parameters:
      - $ref: "#/components/parameters/num_files"

    responses:
      200:
        description: success
    """
    # like jsonify, but with indent
    return current_app.response_class(
        json.dumps(get_app_build_info(query.num_files), indent=4),
        mimetype="application/json",
    )
