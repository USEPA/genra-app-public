"""Domain API utilities."""
from flask import current_app, json

from genraweb.lib.misc import nan_to_none


def frame_response(data, extract=True):
    """Return an object for a domain API call, possibly a GenRAFrame."""
    if extract:
        data = {
            "coldef": data.frame.col_def,
            "rowdef": data.frame.row_def,
            "row": data.frame.row,
        }
    nan_to_none(data)

    return current_app.response_class(
        json.dumps(data, indent=2, sort_keys=False),
        mimetype="application/json",
    )
