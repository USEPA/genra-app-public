"""Definitions for Locust load testing."""
import pathlib

_ids = pathlib.Path(__file__).parent / "ids.lst"
if _ids.is_file():
    with _ids.open() as _f:
        IDS = [line.strip() for line in _f]
        print(f"Loaded {len(IDS)} IDs from {str(_ids)}")
else:
    IDS = ["DTXCID30182"]
    print("No IDs file found, using default ID")
