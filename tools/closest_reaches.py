#!/usr/bin/env python3

import os
import sys
import pathlib
import argparse
import shapely
import pandas as pd
import geopandas as gp
import psycopg2


def rat_tablename(
    dnv: int, order: int = 1, break_lakes: bool = False, break_sites: bool = True
) -> str:
    """Return the rat database for this config"""

    if order == 1:
        return f"rat_dnv{dnv}"
    return f"rat_dnv{dnv}_order{order}_lakes{break_lakes}_sites{break_sites}".lower()


# parse command line
p = argparse.ArgumentParser(
    description="""
Read in lat/lng or easting/northing and output a geopackage with riverlines and
points.  Also print x,y,rid to stdout
""",
    formatter_class=argparse.ArgumentDefaultsHelpFormatter,
)
p.add_argument("infile", type=pathlib.Path, help="Coordinates")
p.add_argument("outfile", type=pathlib.Path, help="Geopackage output")
p.add_argument(
    "--crs", type=int, default=4326, help="CRS of input points (probably 2193 or 4326)"
)
p.add_argument(
    "-d", "--dnv", choices=[1, 2, 3], default=2, help="Digital network version"
)
p.add_argument(
    "-o", "--order", choices=range(1, 10), default=1, help="Aggregaiton order"
)
p.add_argument("-l", action="store_true", dest="break_lakes", help="Break at lakes")
p.add_argument("-s", action="store_true", dest="break_sites", help="Break at sites")
p.add_argument("--dbhost", default="wellhydrodb.niwa.local", help="DB host")
p.add_argument("--dbuser", default="hydrology_user", help="DB user")
p.add_argument("--dbname", default="geometries", help="DB name")
args = p.parse_args()

print(f"Reading in {args.infile}", flush=True)
pts = pd.read_csv(args.infile)

if "REC2CDFPW" not in os.environ:
    sys.stderr.write("Set REC2CDFPW env variable\n")
    sys.exit(1)
dbpasswd = os.environ["REC2CDFPW"]


# connect to database
con = psycopg2.connect(
    host=args.dbhost, user=args.dbuser, password=dbpasswd, database=args.dbname
)
tab = rat_tablename(args.dnv, args.order, args.break_lakes, args.break_sites)


def xy_to_rid(x: float, y: float, crs: int):
    """Return nzreach, geom of closest

    Parameters
    ----------
    x, y: float
        x is easting or longitude (eg 1568375 or 172.6)
        y is northing or latitude (eg 5180479 or -43.5)

    crs: int
        The crs of the point (probably 4326 or 2193)

    Returns
    -------
    tuple:
        (nzreach, geom)
    """

    cur = con.cursor()
    cur.execute(
        f"""
        SELECT nzreach, ST_AsBinary(geom),
        ST_Distance(
            geom,
            ST_Transform(
                ST_SetSRID(ST_MakePoint({x}, {y}), {crs}),
                4326
            )
        ) as dist
        FROM {tab}
        WHERE ST_DWithin(
            geom,
            ST_Transform(
                ST_SetSRID(ST_MakePoint({x}, {y}), {crs}),
                4326
            ),
            0.1
        )
        ORDER BY dist ASC
        LIMIT 1;
    """
    )
    return cur.fetchone()[:2]


rows = []
for _, row in pts.iterrows():
    ret = xy_to_rid(row["x"], row["y"], args.crs)
    rows.append([ret[0], ret[1], shapely.Point(row["x"], row["y"])])
df = gp.GeoDataFrame(rows, columns=["nzreach", "geom", "pt"])
df.geom = df.geom.apply(lambda x: shapely.wkb.loads(bytes(x)))

# pt is in whatever crs passed by user
df.set_geometry("pt", inplace=True)
df.set_crs(args.crs, inplace=True)
# geom is in 4326 from database
df.set_geometry("geom", inplace=True)
df.set_crs(4326, inplace=True)

# best to convert to same crs
df[["nzreach", "pt"]].set_geometry("pt").to_crs(4326).to_file(
    args.outfile, layer="pt", driver="GPKG"
)
df[["nzreach", "geom"]].set_geometry("geom").to_crs(4326).to_file(
    args.outfile, layer="geom", driver="GPKG"
)

# handy to output the pt in 4326
pt4326 = df.set_geometry("pt").to_crs(4326)

print("rid,x,y,lng,lat")
for x, y, rid, pt in zip(pts["x"], pts["y"], df["nzreach"], pt4326.pt):
    print(f"{rid},{x},{y},{pt.x},{pt.y}")
