"""Deployment levels, from most experimental / permissive to least."""
from enum import IntEnum


class DeployType(IntEnum):
    """Deployment levels, from most experimental / permissive to least."""

    LOCAL = 1
    LOCAL_DEV = 2
    DEV = 3
    STG = 4
    PROD = 5
