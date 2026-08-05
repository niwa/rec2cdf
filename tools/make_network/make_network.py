import pathlib
import time
import argparse
import multiprocessing
import functools
import geopandas as gp
import psycopg2
import h5py
import netrc
import shapely.wkb
from typing import List


# so we can time each step
now = None
start = time.time()


def mtime(msg: str):
    """Print a message and start timer"""
    global now
    now = time.time()
    print(msg, end="", flush=True)


def mtime_end():
    """Finish up the timer."""
    print(f"took {(time.time() - now):.2f}s", flush=True)


def spatial_to_lakereaches(fn: pathlib.Path):
    """Return a list of agg rid ID that are associated with a lake

    Parameters
    ----------
    fn: pathlib.Path
        The spatial file
    """

    f = h5py.File(fn, "r")

    return [
        int(rid) for rid, lk in zip(f.get("rchid"), f.get("rch_lakeid")) if lk != -9999
    ]


def read_spatial(fn: pathlib.Path):
    """Return a dict of agg rid ID to ONE agg upstream rid

    We only need one of the upstream aggregate reaches for each reach.  This is
    so we can form the path through this aggregate.

    Parameters
    ----------
    fn: pathlib.Path
        The spatial file
    """

    f = h5py.File(fn, "r")

    return {
        int(rid): up[0] if up[0] != -9999 else None
        for rid, up in zip(f.get("rchid"), f.get("uprch_rchid"))
    }


def trace_up(aid: int, r2u: dict, lakeaids: set) -> List[int]:
    """Return a list of agg rid ID all the way upstream, unless hit a lake

    Parameters
    ----------
    aid: int
        Aggregate reach ID

    r2u: dict
        Agg reach to upstream aggregate

    lakeaids: set
        A set of aggregate reach IDs that are associated with a lake

    Returns
    -------
    list:
        First element is aid, then all the aggregate reach IDs to headwater
        unless we hit a lake, in which case return []
    """

    if aid in lakeaids:
        return []

    ret = [aid]
    up = r2u[aid]

    if up in lakeaids:
        return []

    while up:
        ret.append(up)
        up = r2u[up]
        if up in lakeaids:
            return []

    return ret


def get_downstream_and_order(user: str, pw: str, host: str, db: str, r2info: dict):
    """Get downstream and order info at Strahler 1 from rec1 db."""
    conn = psycopg2.connect(user=user, password=pw, host=host, port="5432", database=db)
    cur = conn.cursor()
    cur.execute("select rchid, lowerreach, streamorder from reach")
    r2info.update({row[0]: {"down": row[1], "order": row[2]} for row in cur.fetchall()})


def get_geoms(user: str, pw: str, host: str, db: str, r2g: dict):
    """Get downstream info at Strahler 1 from rec1 db."""

    conn = psycopg2.connect(user=user, password=pw, host=host, port="5432", database=db)
    cur = conn.cursor()
    cur.execute("select nzreach, geom from riverlines")
    r2g.update(
        {
            int(row[0]): row[1]
            # shapely.wkb.loads(row[1], hex=True)
            for row in cur.fetchall()
        }
    )


def get_member_line(bot: int, r2u: dict, r2d: dict):
    """Return a list of member reaches in this aggregate

    Parameters
    ----------
    bot: int
        The aggregate reach

    r2u: dict
        Agg reach to upstream aggregate

    r2d: dict
        Nonagg reach to downstream reach

    Returns
    -------
    list:
        A list of reaches that connect bot to upstream aggregate reach.
        If there is no upstream the list will only contain bot
    """

    # my upstream aggregate
    up = r2u[bot]

    # if nothing upstream, then bot is the only reach in the aggregate
    if up is None:
        return [bot]

    # start traversing down into this aggregate
    down = r2d[up]
    ret = [down]
    while down != bot:
        down = r2d[down]
        ret.append(down)

    return ret


def member_geom(members: list, r2g: dict):
    return shapely.unary_union([shapely.wkb.loads(r2g[m], hex=True) for m in members])


if __name__ == "__main__":
    # so we can time each step
    now = None
    start = time.time()

    # parse command line
    p = argparse.ArgumentParser(
        description="""
Make network using spatials and rec1 db
Must be spatial files with this format of name in current directory
spatial_rec_09000000_strahler3.nc.

Requires login user and password in your ~/.netrc:
    machine wellhydrodb.niwa.local login USER password PW

        """,
        epilog="""Eg:
        python make_network.py out.gpkg
        """,
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    p.add_argument(
        "--dbhost", type=str, default="wellhydrodb.niwa.local", help="Database hostname"
    )
    p.add_argument("--db", type=str, default="rec1", help="Database name")
    p.add_argument("--crs", type=int, default=3857, help="Output CRS")
    p.add_argument(
        "--prune",
        type=int,
        choices=range(1, 10),
        help="Remove ocean reach (and its upstream) with sorder less than this",
    )
    p.add_argument("spatials", type=pathlib.Path, nargs="+", help="Spatial files")
    p.add_argument("output", type=pathlib.Path, help="Output file")
    args = p.parse_args()

    # get the db password
    nc = netrc.netrc()
    up = nc.hosts[args.dbhost]
    dbuser, dbpass = up[0], up[2]

    manager = multiprocessing.Manager()

    print("Starting process for getting geoms from db...", flush=True)
    r2g = manager.dict()
    p_geoms = multiprocessing.Process(
        target=get_geoms, args=(dbuser, dbpass, args.dbhost, args.db, r2g)
    )
    p_geoms.start()

    print(
        "Starting process for getting strahler 1 downstream info from db...", flush=True
    )
    r2info = manager.dict()
    p_ds = multiprocessing.Process(
        target=get_downstream_and_order,
        args=(dbuser, dbpass, args.dbhost, args.db, r2info),
    )
    p_ds.start()

    ###########################################################################
    mtime("Get an agg upstream reach for each agg reach...")
    r2u = {}
    with multiprocessing.Pool(4) as p:
        for i in p.map(read_spatial, args.spatials):
            r2u.update(i)
    mtime_end()
    ###########################################################################

    ###########################################################################
    mtime("Find all agg reaches associated with a lake...")
    lakeaids = []
    with multiprocessing.Pool(4) as p:
        for i in p.map(spatial_to_lakereaches, args.spatials):
            lakeaids.extend(i)
    lakeaids = set(lakeaids)
    mtime_end()
    ###########################################################################

    # make sure we have downstream and order info
    p_ds.join()

    ###########################################################################
    #
    # Potentially prune out r2u
    #
    if args.prune:
        mtime("Pruning upstream traces from low order ocean aggregates...")
        oceanrids = [
            aid
            for aid in r2u
            if r2info[aid]["down"] is None and r2info[aid]["order"] < args.prune
        ]
        torm = set(u for aid in oceanrids for u in trace_up(aid, r2u, lakeaids))
        print(len(torm))
        r2u = {aid: up for aid, up in r2u.items() if aid not in torm}
        mtime_end()
    ###########################################################################

    ###########################################################################
    mtime("Get member line for each agg...")
    with multiprocessing.Pool(4) as p:
        r2m = {
            rid: line
            for rid, line in zip(
                r2u.keys(),
                p.map(
                    functools.partial(
                        get_member_line,
                        r2d={key: val["down"] for key, val in r2info.items()},
                        r2u=r2u,
                    ),
                    r2u.keys(),
                ),
            )
        }
    mtime_end()
    ###########################################################################

    # make sure we have geoms
    p_geoms.join()

    ###########################################################################
    # maps aggrid to multilinestring for that aggregate
    mtime("Forming multilinestring for each agg...")
    with multiprocessing.Pool(8) as p:
        r2line = {
            rid: geom
            for rid, geom in zip(
                r2m.keys(), p.map(functools.partial(member_geom, r2g=r2g), r2m.values())
            )
        }
    mtime_end()
    ###########################################################################

    mtime(f"Saving to {args.output}...")
    gdf = gp.GeoDataFrame(
        r2line.items(),
        columns=["Top_reach", "geometry"],
        geometry="geometry",
        crs=2193,  # 2193 from rec database
    ).to_crs(epsg=args.crs)
    gdf.to_file(args.output, layer="lines")
    mtime_end()
