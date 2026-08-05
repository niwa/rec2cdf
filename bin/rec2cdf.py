#!/usr/bin/env python3

import os
import sys
import logging
import argparse
import pathlib
import json
import re
import psycopg2
import psycopg2.extras
from netCDF4 import Dataset
from jinja2 import Environment, FileSystemLoader
from itertools import chain
import numpy as np
import datetime as dt

import utils
from flow_stats import FlowStats
from lake import Lake
from soil_veg import Soil_Veg
from wetness import Wetness
from stream_distance import Stream_Distance
from elevation import Elevation
from geom import Geom
from topo import Topo
from water_transfer import Water_Transfer


# To connect to database
dbpasswd = None


def setup_logging(outfile, logfile, lvl, stdout=False):
    """Ensure directories exist and start loggers"""

    for fn in (outfile, logfile):
        fn.parent.mkdir(mode=0o755, parents=True, exist_ok=True)

    logging.getLogger().setLevel(lvl)
    lfmt = logging.Formatter(
        "%(asctime)s %(levelname)-8s %(message)s", datefmt="%a, %d %b %Y %H:%M:%S"
    )

    fhand = logging.FileHandler(logfile, mode="w")
    fhand.setFormatter(lfmt)
    logging.getLogger().addHandler(fhand)

    # uncaught exceptions to the logfile via this function
    sys.excepthook = handle_exception

    # maybe send logging to stdout too
    if stdout:
        shand = logging.StreamHandler(sys.stdout)
        shand.setFormatter(lfmt)
        logging.getLogger().addHandler(shand)

    return fhand


# any uncaught exceptions go to log file
def handle_exception(exc_type, exc_value, exc_traceback):
    if issubclass(exc_type, KeyboardInterrupt):
        sys.__excepthook__(exc_type, exc_value, exc_traceback)
        return

    logging.critical("Uncaught exception", exc_info=(exc_type, exc_value, exc_traceback))


def rid_to_db(rid):
    """Return the rec3 database for this range of reaches

    Parameters
    ----------
    rid: int
        Reach ID, from 1e6 up to just less than 16e6

    Returns
    -------
    str:
        The name of the REC3 database to use
    """

    assert 1e6 <= rid < 16e6

    # maps nzreach to which dn3 db
    dn3db = [
        "northland",
        "auckland",
        "waikato",
        "nieast",
        "nieast",
        "taranaki",
        "taranaki",
        "nieast",
        "wellington",
        "tasman",
        "marlborough",
        "wcoast",
        "canterbury",
        "otago",
        "southland",
    ]

    return f"dn3_{dn3db[int(rid // 1e6) - 1]}"


def get_code_version() -> str:
    """Return code version or 'unknown' if version.txt doesn't exist"""

    mydir = pathlib.Path(__file__).resolve().parent
    version_file = mydir / "version.txt"
    try:
        with open(version_file, "r") as fh:
            ma = re.match(r"Version: (.*)", fh.read())
            if ma:
                return ma.group(1)
    except Exception:
        pass

    return "unknown"


def get_db_version(con: psycopg2.extensions.connection) -> str:
    """Return DB version or 'unknown' if tables not setup"""
    try:
        cur = con.cursor()
        cur.execute("SELECT version, date FROM changelog")
        ret = cur.fetchall()[-1]
        if ret:
            cur.close()
            return f"{ret[0]} ({ret[1]})"
    except Exception:
        pass

    return "unknown"


def set_metadata(output, attrs):
    """Get Global attributes from jinja, and set the metadata in output"""

    logging.debug(f"Setting Global attributes in {output}")
    mydir = pathlib.Path(__file__).resolve().parent
    template = Environment(loader=FileSystemLoader(searchpath=mydir)).get_template(
        "attr_info.jinja"
    )
    kv = json.loads(template.render(attrs))["global"]

    logging.info(f"Maximum number of reaches per agg {attrs['maxe']}")
    logging.info(f"Maximum number of distribution bins per agg {attrs['maxbins']}")
    logging.info(f"Maximum number of upstreams per agg {attrs['maxup']}")
    with Dataset(output, "w", format="NETCDF4") as ncid:
        for key, val in kv.items():
            setattr(ncid, key, val)
        ncid.createDimension("maxe", attrs["maxe"])
        ncid.createDimension("maxbins", attrs["maxbins"])
        ncid.createDimension("maxup", attrs["maxup"])
        ncid.createDimension("water_transfer_endpts", attrs["water_transfer_endpts"])


def get_lake_data(con: psycopg2.extensions.connection) -> list:
    """Return list of reaches that touch a lake

    Parameters
    ----------
    con: psycopg2.extensions.connection
        Connection to dn1, dn2 or dn3 database

    Returns
    -------
    list
        A list of reach IDs that intersect with a lake
    """

    cur = con.cursor()
    q = """
        SELECT DISTINCT rchid FROM reach 
        WHERE rchid > 0 AND (
            fnode IN
            (SELECT r.fnode FROM reach r INNER JOIN lake l ON (r.rchid = l.ds_rchid))
            OR tnode IN
            (SELECT r.fnode FROM reach r INNER JOIN lake l ON (r.rchid = l.ds_rchid))
        ) ORDER BY rchid
    """
    logging.info("Finding reaches that touch a lake")
    logging.debug(f"Lake query {q}")
    cur.execute(q)
    ret = [int(row[0]) for row in cur.fetchall()]
    logging.info(f"got {len(ret)} lakes")
    return ret


def get_all_station_rchids(con: psycopg2.extensions.connection) -> list:
    """Return a list of reach IDs belonging to all flow stations

    Parameters
    ----------
    con: psycopg2.extensions.connection
        Connection to dn1, dn2 or dn3 database

    Returns
    -------
    list
        A list of rchids associated with flow stations
    """

    cur = con.cursor()
    q = """
        SELECT rchid
        FROM wlsites
        WHERE rchid >= 0 AND lat<>'0' AND lon<>'0'
    """
    logging.info("Finding station/site rchids")
    logging.debug(f"Station query {q}")
    cur.execute(q)
    ret = [int(row[0]) for row in cur.fetchall()]
    logging.info(f"got {len(ret)} sites")
    return ret


def append_station_vars(
    con: psycopg2.extensions.connection,
    outfile: pathlib.Path,
    rchids: list,
    attrsdict: dict,
):
    """Append station/site variables to spatial file

    Stations with rchid in the given list rchids are included in spatial file

    Parameters
    ----------
    con: psycopg2.extensions.connection
        Connect to postgresql dn database

    outfile: pathlib.Path
        Already existing spatial file without station variables

    rchids: list
        A list of rchids, probably aids, that are in our catchment
    """

    logging.info("Open netcdf file for appending station/site data")
    nc = Dataset(outfile, "a", format="NETCDF4")

    # get stations that are in our catchment defined by given rchids
    q = f"""
        SELECT siteno AS station_id,
        trim(river)||' at '||trim(sitename) AS station_name,
        lat AS station_lat,
        lon AS station_lon,
        altitude AS station_altitude,
        rchid AS station_rchid,
        uparea AS station_uparea
        FROM wlsites
        WHERE rchid IN ({','.join(map(str, rchids))}) AND lat<>'0' AND lon<>'0'
    """
    logging.info("fetching station/site info")
    logging.debug(f"executing SQL {q}")
    cur = con.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
    cur.execute(q)

    # a dict from variable name to a list of values for that variable
    v2val = {}
    for row in cur.fetchall():
        for key, val in row.items():
            v2val.setdefault(key, []).append(val)

    logging.info("setting global station/site attributes")
    num_sites = len(v2val.get("station_id", []))
    setattr(nc, "no_of_river_flow_rate_stations", num_sites)
    setattr(nc, "river_flow_rate_station_dimension", "station")

    # if no stations/sites we are done
    if num_sites == 0:
        logging.warning("no stations/sites in catchment, no info to add")
        nc.close()
        return

    # station_nrch variable is a list of rchid index values
    r2i = {r: i for i, r in enumerate(rchids)}
    v2val["station_nrch"] = list(map(r2i.get, v2val["station_rchid"]))

    # station variable is just 0, 1, ...
    v2val["station"] = list(range(num_sites))

    logging.info("creating station and station_name_length dimensions")
    max_name_len = 80
    nc.createDimension("station", num_sites)
    nc.createDimension("station_name_length", max_name_len)

    # get the types and attributes for the station variables
    mydir = pathlib.Path(__file__).resolve().parent
    template = Environment(loader=FileSystemLoader(searchpath=mydir)).get_template(
        "attr_info.jinja"
    )
    v2info = json.loads(template.render(attrsdict))["station_vars"]

    # make the variables
    for v, info in v2info.items():
        logging.debug(f"creating variable {v}")
        var = nc.createVariable(
            v, info["type"], info["dims"], fill_value=info.get("fillvalue", None)
        )

        # topnet can't handle proper strings, so station_name must be an
        # array of 1-length strings
        if info["type"] == "S1":
            for i, name in enumerate(v2val[v]):
                for j in range(min(len(name), max_name_len)):
                    var[i, j] = name[j]
        else:
            var[:] = v2val[v]

        for key, val in info["attributes"].items():
            setattr(var, key, val)

    nc.close()
    logging.info(f"appended station data to {outfile}")


def gen_spatial(
    outfile: pathlib.Path,
    rids: list,
    con: psycopg2.extensions.connection,
    order: int,
    break_lakes: bool,
    break_sites: bool,
    regional: bool,
    truncates: list,
):
    """Create spatial file.  This is the main entry point of rec2cdf

    Parameters
    ----------

    outfile: pathlib.Path
        Name of spatial file to generate

    rids: list
        List of reach IDs whose catchments will be included

    con: psycopg2.extensions.connection
        Connection to correct (dn1, dn2, dn3_*) database

    order: int
        Strahler aggregation order

    break_lakes: bool
        Whether to break at lakes

    break_sites: bool
        Whether to break at sites

    regional: bool
        Do the regions containing rids

    truncates: list
        A list of reach IDs to truncate network at.  These and further upstream
        will not be included

    Returns
    -------
    list:
        Aggregate ids, or [] if an error
    """

    # we keep these rchid if in catchment regardless of aggregation
    extra = []
    if break_sites:
        extra = get_all_station_rchids(con)
    if break_lakes:
        extra.extend(get_lake_data(con))

    # if regional, get all terms to start from
    mil = 1000000
    if regional:
        # user could have specified a bunch of rids, they might even be in
        # different regions
        terms = [utils.terms(con, mil * (r // mil), mil * (r // mil + 1)) for r in rids]
        # flatten/remove dups.
        rids = list(set(chain.from_iterable(terms)))
        logging.info(f"{len(rids)} terminals from {min(rids)} to {max(rids)}")

    logging.info(
        "Spatial file for "
        f"{(mil * (min(rids)//mil), mil * (max(rids)//mil + 1)) if regional else rids}"
        f", order {order}, output {outfile}"
    )

    # trace up from all the rids, checking they are aggids first
    a2info = {}
    r2info = {}
    for r in rids:
        if utils.aggid_for_rid(con, r, order, extra) != r:
            logging.error(
                f"{r} not in order {order} network.  Closest downstream "
                "aggregate reach is "
                f"{utils.aggid_for_rid(con, r, order, extra)}"
            )
            return []
        ar = utils.agg_up(con, r, order, set(extra), truncates)
        a2info.update(ar["agg"])
        r2info.update(ar["reach"])

    # maximum number of reaches per agg
    maxe = max(len(info["rids"]) for info in a2info.values())
    # maxe = 6000
    maxup = max(len(info["ups"]) for info in a2info.values())

    # attributes for attr_info.jinja
    attrsdict = {
        "water_transfer_endpts": 2,
        "maxe": maxe,
        "maxbins": 200,
        "maxup": maxup,
        "default_mannings": 0.024,
        "stream_width_a": 0.001107,
        "stream_width_b": 0.518,
        "max_i4": np.iinfo("int32").max,
        "catchrchid": rids[0],
        "condsn": con.dsn,
        "now": dt.datetime.today().isoformat(),
        "code_version": get_code_version(),
        "db_version": get_db_version(con),
        "no_sub_catchments": len(a2info),
        "truncate_rchids": ",".join(map(str, truncates)) if truncates else "",
        "region": f"{'south' if rids[0] >= 10e6 else 'north'}-island",
    }

    # start with no output file
    outfile.unlink(missing_ok=True)

    # put global attributes in
    set_metadata(outfile, attrsdict)

    # do the variables
    top = Topo(attrsdict, outfile, con, truncates, a2info, r2info)
    for cls in (Geom, FlowStats, Soil_Veg, Wetness, Stream_Distance, Elevation):
        cls(attrsdict, outfile, con, top)

    if break_lakes:
        Lake(attrsdict, outfile, con, top)
        Water_Transfer(attrsdict, outfile, con, top)

    if top.aids:
        append_station_vars(con, outfile, top.aids, attrsdict)

    return top.aids


if __name__ == "__main__":
    p = argparse.ArgumentParser(
        description="""
    Generate netCDF spatial data from postgresql for TopNet starting from
    given starting reach
    """,
        formatter_class=argparse.ArgumentDefaultsHelpFormatter,
    )
    p.add_argument("rids", type=int, nargs="+", help="Catchment reach ID")
    p.add_argument(
        "-d",
        "--dbname",
        default="dn25",
        help="Database name (probably rec1, dn23, dn25 or dn3)",
    )
    p.add_argument(
        "-o",
        "--order",
        type=int,
        choices=range(1, 10),
        default=1,
        help="The aggregation Strahler order",
    )
    p.add_argument("-l", action="store_true", dest="break_lakes", help="Break network at lakes")
    p.add_argument("-s", action="store_true", dest="break_sites", help="Break network at sites")
    p.add_argument(
        "--extrarids", type=pathlib.Path, help="One rchid per line of extra catchment rids"
    )
    p.add_argument(
        "--regional",
        action="store_true",
        help="Generate spatial file for region containing rid",
    )
    p.add_argument(
        "--dbhost", type=str, default="wellhydrodb.niwa.local", help="Database hostname"
    )
    p.add_argument("--dbuser", type=str, default="hydrology_user", help="Database username")
    p.add_argument(
        "--truncates",
        type=lambda arg: list(map(int, arg.split(","))),
        default=[],
        help="A comma separated list of rids to truncate network before",
    )
    p.add_argument("--outfile", type=pathlib.Path, help="NetCDF output file")
    p.add_argument("--logfile", type=pathlib.Path, help="Defaults to outfile with .log suffix")
    p.add_argument(
        "--loglevel",
        type=str,
        choices=["debug", "info", "warning", "error", "critical"],
        default="info",
        help="Log level",
    )
    args = p.parse_args()

    if args.extrarids:
        with open(args.extrarids) as fh:
            try:
                args.rids.extend([int(line.strip()) for line in fh if line.strip()])
            except ValueError as exp:
                logging.error(f"{args.extrarids} should contain one rid per line: {exp}")
                sys.exit(1)
            # other errors can be handled by the default handler
        args.rids = list(set(args.rids))

    # if dn3, all rids must be in same region
    if args.dbname == "dn3":
        reg = int(args.rids[0] // 1e6)
        if not all(int(rid // 1e6) == reg for rid in args.rids):
            logging.error(f"For DN3 all rids must be in same region: {args.rids}")
            sys.exit(1)

    # if dn3 we need to get more specific
    args.dbname = rid_to_db(args.rids[0]) if args.dbname in ("dn3", "rec3") else args.dbname

    # if the db password is not hard coded in here, it better be in an environment
    # var the gui will set that up
    if dbpasswd is None:
        if "REC2CDFPW" not in os.environ:
            sys.stderr.write("Must set db password in rec2cdf.py, or REC2CDFPW env variable\n")
            sys.exit(1)
        dbpasswd = os.environ["REC2CDFPW"]

    # netcdf output and log file names
    if not args.logfile:
        args.logfile = args.outfile.with_suffix(".log")

    setup_logging(args.outfile, args.logfile, args.loglevel.upper(), stdout=True)

    # connect to database
    dbcon = psycopg2.connect(
        host=args.dbhost, user=args.dbuser, password=dbpasswd, database=args.dbname
    )

    if not gen_spatial(
        args.outfile,
        args.rids,
        dbcon,
        args.order,
        args.break_lakes,
        args.break_sites,
        args.regional,
        args.truncates,
    ):
        logging.error(f"Something went wrong, removing incomplete {args.outfile}")
        args.outfile.unlink(missing_ok=True)
        sys.exit(1)
