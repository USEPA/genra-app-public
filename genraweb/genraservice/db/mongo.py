import getpass
import os

import pymongo

from genraweb.lib.logging import logger


def openMongo(host="pb.epa.gov", user=None, passwd=None, db=None, auth=True):
    if auth:
        if not user or passwd:
            user, passwd = (
                open(os.getenv("HOME") + "/.mngdb/passwd").read().strip().split(":")
            )

        con2 = pymongo.MongoClient("mongodb://%s:%s@%s/%s" % (user, passwd, host, db))
        DB = con2[db]
    else:
        con2 = pymongo.MongoClient("mongodb://%s/%s" % (host, db))
        DB = con2[db]
    return DB


def getMongoCred(path="~/.mngdb/passwd"):
    user, passwd = open(os.getenv("HOME") + "/.mngdb/passwd").read().strip().split(":")
    return dict(user=user, passwd=passwd)


def openAdmin(host="localhost", user="admin", auth=True):
    if auth:
        pwd = getpass.getpass(prompt="Admin Passwd:")
        con = pymongo.MongoClient("mongodb://%s:%s@%s:27017/admin" % (user, pwd, host))
    else:
        con = pymongo.MongoClient("mongodb://%s:27017/admin" % (host))

    if con.address is not None:
        logger.info("Success")
    else:
        logger.info("Failed")

    return con


def createDB(db, con):
    if db in con.database_names():
        logger.info(("Database: %s exists" % db))
        return

    dbc = con[db]
    dbc["test"].insert_one(dict(a=1))
    # dbc.test.drop()


def addUser(db, con, user, roles):
    dbc = con[db]
    user_pwd1 = getpass.getpass(prompt="User Passwd:")
    user_pwd2 = getpass.getpass(prompt="Repeat:")

    if user_pwd1 == user_pwd2:
        logger.info(
            "Creating user:%s with roles: %s in db: %s",
            user,
            ",".join(roles),
            db,
        )
        dbc.command("createUser", user, pwd=user_pwd1, roles=roles)
    else:
        logger.info("Password mismatch")


def registerMongoEngine(alias, host="pb.epa.gov", user=None, passwd=None, db=None):
    if not user or passwd:
        user, passwd = (
            open(os.getenv("HOME") + "/.mngdb/passwd").read().strip().split(":")
        )
    mongoengine.register_connection(
        alias, host="mongodb://%s:%s@%s/%s" % (user, passwd, host, db)
    )
