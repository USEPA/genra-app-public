import os
import urllib
from functools import partial
from itertools import cycle

import pymongo

from genraweb.lib.logging import logger


def get_param(user, pw, port, host, patience):
    """
    get_param - Calculate params (as dict) for inputs, inputs given as '' are
    unspecified.

    Args:
        user (str): username
        pw (str): password
        port (str): port
        host (str): host
        patience (int): serverSelectionTimeoutMS
    Returns:
        dict: params to use in connect(**params)
    """
    if port:
        port = int(port)
    param = dict(
        host=host,
        serverSelectionTimeoutMS=patience,
    )
    if user:
        param["username"] = user
    if pw:
        param["password"] = pw
    if port:
        param["port"] = port
    return param


def get_uri(user, pw, port, host, db, kwargs, patience, connect_db):
    """
    get_uri - Calculate uri for inputs, inputs given as '' are unspecified.

    Args:
        user (str): username
        pw (str): password
        port (str): port
        host (str): host
        db (str): database name
        connect_db (str): auth database name
        kwargs (str): key0:val0&key1:val1 string
    Returns:
        str: URI for connection"""

    template = "mongodb://{auth}{host}/{db}?serverSelectionTimeoutMS={patience}{kwargs}"

    if connect_db:
        if kwargs:
            kwargs = f"{kwargs}&authSource={connect_db}"
        else:
            kwargs = f"authSource={connect_db}"

    user = urllib.parse.quote_plus(user, safe="")
    pw = urllib.parse.quote_plus(pw, safe="")
    kwargs = "&" + urllib.parse.quote_plus(kwargs, safe="=&") if kwargs else ""
    if port:
        # Given host aaa,bbb,ccc and port xxx,yyy, make host string
        # aaa:xxx,bbb:yyy,ccc:xxx - typically just one port repeated over all hosts
        hosts = host.split(",")
        ports = port.split(",")
        hosts = [f"{host}:{port}" for host, port in zip(hosts, cycle(ports))]
        host = ",".join(hosts)

    make_uri = partial(
        template.format, host=host, db=db, patience=patience, kwargs=kwargs
    )
    # log a redacted URI
    auth = "user" + (":" + "pword" if pw else "") + "@" if user else ""
    uri = make_uri(auth=auth)
    logger.info(uri)
    # calculate real URI
    auth = user + (":" + pw if pw else "") + "@" if user else ""
    uri = make_uri(auth=auth)
    if os.environ.get("GENRA_DUMP_DB_URI"):
        # convenience method for getting connection strings
        print(uri)
    return uri


def get_genra_db_env_var(which, field, default=None):
    """
    gets GENRA_DB environment variable for <FIELD>, for the nearest matching <WHICH>.

    Show by example.
    Let there be the following variables defined in our system:
    GENRA_DB_PB_V1_FIELDX=PB_V1_FIELDXVAL
    GENRA_DB_FIELDX=FIELDXVAL
    Then:
    get_genra_db_env_var("PB_V1", "FIELDX") => "PB_V1_FIELDXVAL"
    get_genra_db_env_var("PB_VDNE", "FIELDX") => "FIELDXVAL"
    get_genra_db_env_var("DNE_VDNE", "FIELDX") => "FIELDXVAL"
    get_genra_db_env_var("", "FIELDX") => "FIELDXVAL"
    """

    required_fields = ["HOST"]

    left = "GENRA_DB_"
    right = "_" + field

    def find_env_var(curr_which):
        """Get an env. var. from os.environ.

        Returns (specified, value)

        `specified` - env. var. explicitly set to a (possibly blank) value
        `value` - the value or default if not set
        """
        env_var_name = left + curr_which + right if curr_which else left + right[1:]
        return env_var_name in os.environ, os.environ.get(env_var_name, default)

    safety = 5
    curr_which = which
    while True:
        specified, env_var = find_env_var(curr_which)
        if specified:
            # if found
            break
        if not curr_which and field in required_fields:
            # if done traversing through <WHICH> (i.e., tried root but that failed too)
            # and required
            raise Exception(
                "Environment variable (or its relatives) "
                "{left}{which}{right} not found.".format(
                    left=left, which=which, right=right
                )
            )
        elif not curr_which and not env_var:
            # if it's a blank or can't find variable
            env_var = default
            break
        elif safety <= 0:
            env_var = default
            break
        # keep searching
        safety -= 1
        if "_" in curr_which:
            # there's a 'parent'
            curr_which = "_".join(curr_which.split("_")[:-1])
        else:
            # no more parents except for the root
            curr_which = ""
    return env_var


def open_mongo_db(which="", seconds=5):
    """Opens a mongo connection using environment variables defined in .env, and
    returns the pymongo database object.

    For simplicity, we will say there is the "args" method and the "uri" method
    for connection.  If GENRA_DB_USE_URI is set to 0, it first tries the args
    method and then tries the uri method.  If GENRA_DB_USE_URI is set to 1,
    vice versa. In other words, GENRA_DB_USE_URI only determines which method
    is tried first.

    Args:
    which (str): default will use GENRA_DB_<FIELD>
    seconds (int): The number of seconds to set the
    serverSelectionTimeoutMS . The default is no longer set to the same as the pymongo
    default of 30 seconds, but rather to 5 seconds, to prevent th worker thread to
    prematuraly close the connection attempt and restart
    """

    patience = seconds * 1000  # serverSelectionTimeoutMS is in milliseconds

    host = get_genra_db_env_var(which, "HOST")
    db = get_genra_db_env_var(which, "DB", "")
    connect_db = get_genra_db_env_var(which, "CONNECT_DB", "")
    user = get_genra_db_env_var(which, "USER", "")
    pw = get_genra_db_env_var(which, "PASS", "")
    # default mongo port is 27017, but let tools apply defaults
    port = get_genra_db_env_var(which, "PORT", "")
    kwargs = get_genra_db_env_var(which, "KWARGS", "")

    use_uri = get_genra_db_env_var(which, "USE_URI") or "0"

    def connect_with_args():
        return pymongo.MongoClient(
            **get_param(user, pw, port, host, patience), maxPoolSize=500
        )

    connect_with_args.description = "Keyword args connector"

    def connect_with_uri():
        return pymongo.MongoClient(
            get_uri(user, pw, port, host, db, kwargs, patience, connect_db),
            maxPoolSize=500,
        )

    connect_with_uri.description = "URI connector"

    def get_valid_client(client_connector):
        try:
            client = client_connector()
            client.server_info()
            return client, None
        except Exception as e:
            logger.error(
                "Connector '%s' failed: %s", which, client_connector.description
            )
            if (
                isinstance(e, pymongo.errors.OperationFailure)
                and "Authentication failed." in str(e)
                or isinstance(e, pymongo.errors.ServerSelectionTimeoutError)
            ):
                # A connection problem that we've seen before
                return None, e
            raise e

    client_connectors = [connect_with_uri, connect_with_args]
    if use_uri == "0":
        client_connectors.reverse()  # change order

    for client_connector in client_connectors:
        valid_client, connection_error = get_valid_client(client_connector)
        if valid_client:
            logger.info("Connect '%s' OK: %s", which, client_connector.description)
            db_connection = valid_client.get_database(db)
            db_connection._uri = get_uri(
                user, pw, port, host, db, kwargs, patience, connect_db
            )
            return db_connection
    raise connection_error
