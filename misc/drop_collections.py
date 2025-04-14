"""
drop_collections.py - drop OR RENAME mongo collections by pattern, useful for cleanup.

Terry N. Brown Brown.TerryN@epa.gov Sun 18 Jul 2021 03:30:22 PM UTC
"""
import cmd
import re

from genraweb.lib.db_connection import open_mongo_db

cli = cmd.Cmd()


def show_list(list_):
    """https://stackoverflow.com/a/59627245/1072212"""
    cli.columnize(sorted(list_), displaywidth=120)


which = input("* Which DB? DEV / STG / PROD etc.: ")
src = open_mongo_db(which=which)
src_coll = src.list_collection_names()
show_list(src_coll)

pattern = input("* Pattern (a|b|c matches a, b, and c): ")
src_coll = [i for i in src_coll if re.search(pattern, i)]
show_list(src_coll)

pattern = input("* Enter DROP to drop, RENAME to rename: ")
if pattern == "DROP":
    for coll in src_coll:
        src[coll].drop()
else:
    prefix = input("* Enter prefix for renaming: ")
    todo = []
    for coll in src_coll:
        print(f"{coll} -> {prefix+coll}")
        if prefix + coll in src_coll:
            print("    Already exists, skipping")
        else:
            todo.append(coll)
    pattern = input("* Enter RENAME to rename: ")
    if pattern == "RENAME":
        for coll in todo:
            src[coll].rename(prefix + coll)
