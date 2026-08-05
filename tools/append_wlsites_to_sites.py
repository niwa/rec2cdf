#!/usr/bin/env python3
#

import os
import sys
import argparse
import psycopg2
import geopandas as gp
from sqlalchemy import create_engine

p = argparse.ArgumentParser(
    description="""
Update sites table (made from pypop repo m2pkg) with extra flow sites from wlsites tables
""",
    formatter_class=argparse.ArgumentDefaultsHelpFormatter,
)
p.add_argument("--dbhost", type=str, default="wellhydrodb.niwa.local", help="Database hostname")
p.add_argument("--dbuser", type=str, default="hydrology_user", help="Database username")
args = p.parse_args()

if "REC2CDFPW" not in os.environ:
    sys.stderr.write("Must set db password in rec2cdf.py, or REC2CDFPW env variable\n")
    sys.exit(1)
dbpasswd = os.environ["REC2CDFPW"]

# get current sites
engine = create_engine(f"postgresql+psycopg2://{args.dbuser}:{dbpasswd}@{args.dbhost}:5432/geometries")
sdf = gp.read_postgis("select * from sites", engine)

# this is what we will add to sites
sid2info = {}

# now get the sites from dn1, dn23, dn25, dn3
name_diffs = 0
geom_diffs = 0
for db in reversed(['rec1', 'dn23', 'dn25', 'dn3_auckland', 'dn3_canterbury', 'dn3_marlborough', 'dn3_nieast', 'dn3_northland', 'dn3_otago', 'dn3_southland', 'dn3_taranaki', 'dn3_tasman', 'dn3_waikato', 'dn3_wcoast', 'dn3_wellington']):
    sql = f"""
        select
            siteno as site,
            rchid,
            trim(river) || ' at ' || trim(sitename) AS name,
            ST_SetSRID(ST_MakePoint(lon, lat), 4326) AS geom
        from wlsites
        where lon is not null and lat is not null
    """
    engine = create_engine(f"postgresql+psycopg2://{args.dbuser}:{dbpasswd}@{args.dbhost}:5432/{db}")
    sdf = gp.read_postgis(sql, engine)

    if db == 'rec1':
        rkey = 'rid_dn1'
    elif db == 'dn23':
        rkey = 'rid_dn2.3'
    elif db == 'dn25':
        rkey = 'rid_dn2.5'
    elif db.startswith('dn3_'):
        rkey = 'rid_dn3'

    # try and add our new info to sid2info
    for _, row in sdf.iterrows():
        if row.site not in sid2info:
            sid2info[row.site] = {
                'name': row['name'],
                'rid_dn1': None,
                'rid_dn2.3': None,
                'rid_dn2.5': None,
                'rid_dn3': None,
                'geom': row.geom
            }
            sid2info[row.site][rkey] = row.rchid
        else:
            # already in there, we need to do some consistency checks
            if row.geom.distance(sid2info[row.site]['geom']) > 1e-4:
                print(f"WARNING: already have {row.site} {sid2info[row.site]} BUT {db} has geom {row.geom}")
                geom_diffs += 1
                continue
            if row['name'] != sid2info[row.site]['name']:
                print(f"WARNING: already have {row.site} {sid2info[row.site]} BUT {db} has name {row['name']}")
                name_diffs += 1
                continue
            sid2info[row.site][rkey] = row.rchid

print(f"Read in new info, there were {geom_diffs} geometry diffs, and {name_diffs} name diffs")

# sid2info to a gdf
gdf = gp.GeoDataFrame(
    [
        {
            "site": site,
            "name": info["name"],
            "rid_dn1": info["rid_dn1"],
            "rid_dn2.3": info["rid_dn2.3"],
            "rid_dn2.5": info["rid_dn2.5"],
            "rid_dn3": info["rid_dn3"],
            "start": None,
            "end": None,
            "var": "flow",
            "geom": info["geom"],
        }
        for site, info in sid2info.items()
    ],
    geometry="geom", crs="EPSG:4326"
)
print(gdf)

print("Appending gdf to sites")
engine = create_engine(f"postgresql+psycopg2://{args.dbuser}:{dbpasswd}@{args.dbhost}:5432/geometries")
gdf.to_postgis("sites", engine, if_exists="append", index=False)


