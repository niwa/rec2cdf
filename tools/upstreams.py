#!/usr/bin/env python

import sys
import pathlib
import argparse
from netCDF4 import Dataset


# parse command line
p = argparse.ArgumentParser(
    description="""
Read in spatial file, and output a csv with upstream traces.
There is a row for each reach, and the row contains the trace.

Eg suppose the network is:
   1     2
    |   /
      3     5
      |     |
      4 ---/
the output would be
4,3,1,2,5
3,1,2
1
2
5

Optionally you can pass -r <rid> and only tracing from that reach
will be performed.
""",
    formatter_class=argparse.ArgumentDefaultsHelpFormatter,
)
p.add_argument("infile", type=pathlib.Path, help="Spatial file")
p.add_argument("-r", "--rid", type=int, help="Trace from this reach")
p.add_argument("-v", "--verbose", action="store_true", help="Verbose output")
args = p.parse_args()

if args.verbose:
    print(f"Reading in {args.infile}...", flush=True)
ds = Dataset(args.infile, "r")

# maps reach id to parents (so only a list of length 0, 1, 2, or
# possibly 3)
if args.verbose:
    print("Building immediate upstream datastructure...", flush=True)
r2p = {
    int(rid): list(row.compressed())
    for rid, row in zip(ds.variables["rchid"], ds.variables["uprch_rchid"])
}
ds.close()

# this maps rid to the full upstream trace
r2ups = {}


def ups(rid: int) -> list:
    """Return a list of upstreams

    Uses r2ups as a cache to save recalculating

    Parameters
    ----------
    rid: int
        Reach to start at

    Returns
    -------
    list
        First element is rid, then all the upstream reaches
    """
    if rid in r2ups:
        return r2ups[rid]

    ret = [rid]
    for r in r2p[rid]:
        ret.extend(ups(r))
    return ret


if args.rid:
    if args.rid in r2p:
        print(",".join(map(str, ups(args.rid))))
    else:
        sys.stdout.write(f"{args.rid} is not a valid reach ID\n")
        sys.exit(1)
else:
    for rid in r2p.keys():
        print(",".join(map(str, ups(rid))))
