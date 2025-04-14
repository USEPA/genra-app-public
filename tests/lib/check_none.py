"""Helper(s) to be used pertaining to None values"""


def check_None_in_dict(d):
    """Check that dict d contains None values"""
    if not isinstance(d, (dict, list)):
        return False
    for v in d if isinstance(d, list) else d.values():
        if v is None or check_None_in_dict(v):
            return True
    return False
