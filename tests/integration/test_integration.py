import os
import sys
import pathlib
import psycopg2
import tempfile
import xarray as xr
import numpy as np
from rec2cdf import gen_spatial

dbhost = "wellhydrodb.niwa.local"
dbuser = "hydrology_user"
if "REC2CDFPW" not in os.environ:
    sys.stderr.write("Must set db password in rec2cdf.py, or REC2CDFPW env variable\n")
    sys.exit(1)
dbpasswd = os.environ["REC2CDFPW"]


def test_dn2s1small(dn2s1small):
    handle, out = tempfile.mkstemp()
    out = pathlib.Path(out)
    con = psycopg2.connect(host=dbhost, user=dbuser, password=dbpasswd, database="dn25")
    mine = gen_spatial(out, [14194105], con, 1, True, True, False, [])
    mine = xr.open_dataset(out)
    np.testing.assert_array_equal(
        np.sort(mine.rchid.values),
        np.sort(
            np.array(
                [
                    14194105.0,
                    14194217.0,
                    14194218.0,
                    14194219.0,
                    14194289.0,
                    14194588.0,
                    14194623.0,
                ]
            )
        ),
    )
    xr.testing.assert_allclose(dn2s1small, mine)
    os.unlink(out)


def test_truncated(truncated):
    handle, out = tempfile.mkstemp()
    out = pathlib.Path(out)
    con = psycopg2.connect(host=dbhost, user=dbuser, password=dbpasswd, database="dn25")
    mine = gen_spatial(out, [13146864], con, 2, True, True, False, [13145227, 13145209])
    mine = xr.open_dataset(out)
    xr.testing.assert_allclose(truncated, mine)
    os.unlink(out)


def test_truncated_uparea(truncated):
    handle, out = tempfile.mkstemp()
    out = pathlib.Path(out)
    con = psycopg2.connect(host=dbhost, user=dbuser, password=dbpasswd, database="dn25")
    mine = gen_spatial(out, [13146864], con, 2, True, True, False, [])
    mine = xr.open_dataset(out)
    np.testing.assert_array_equal(
        np.sort(mine.uparea.values),
        np.sort(
            np.array(
                [
                    29990910.0,
                    18340186.0,
                    10073877.0,
                    2513764.5,
                    7102900.0,
                    2891823.3,
                    14761638.0,
                    7393037.0,
                    4735110.0,
                    2211420.8,
                    5095212.5,
                    3650436.8,
                    1450871.1,
                    732614.0,
                    2318493.0,
                    1647010.6,
                    1275316.9,
                ]
            )
        ),
    )
    mine = gen_spatial(out, [13146864], con, 2, True, True, False, [13145227, 13145209])
    mine = xr.open_dataset(out)
    np.testing.assert_almost_equal(
        np.sort(mine.uparea.values),
        np.sort(
            np.array(
                [
                    21865257.812031,
                    10947148.372941,
                    9341263.76771,
                    2513764.6537,
                    6370286.45461,
                    2891823.411302,
                    7368601.844139,
                    1450871.0369,
                    2318493.029589,
                    1647010.6985,
                    1275316.9466,
                ]
            )
        ),
    )
    os.unlink(out)


def test_lotsalakes(lotsalakes):
    handle, out = tempfile.mkstemp()
    out = pathlib.Path(out)
    con = psycopg2.connect(host=dbhost, user=dbuser, password=dbpasswd, database="dn25")
    for d in (2,):
        for o in (1, 2, 3):
            for ll in (True, False):
                for s in (True, False):
                    fix = lotsalakes[f"{d}{o}{ll}{s}"]
                    mine = gen_spatial(out, [13172090], con, o, ll, s, False, [])
                    mine = xr.open_dataset(out)
                    try:
                        xr.testing.assert_allclose(fix, mine, rtol=0.1)
                    except Exception as exp:
                        print(f"Failed on lal {d=} {o=} {ll=} {s=}.  Full error {exp}")
                    os.unlink(out)


def test_sigabovenonsig(sigabovenonsig):
    handle, out = tempfile.mkstemp()
    out = pathlib.Path(out)
    con = psycopg2.connect(host=dbhost, user=dbuser, password=dbpasswd, database="dn25")
    for d in (2,):
        for o in (1, 2, 3):
            for ll in (True,):
                for s in (True,):
                    fix = sigabovenonsig[f"{d}{o}{ll}{s}"]
                    mine = gen_spatial(out, [13173665], con, o, ll, s, False, [])
                    mine = xr.open_dataset(out)
                    try:
                        xr.testing.assert_allclose(fix, mine)
                    except Exception as exp:
                        print(f"Failed on sans {d=} {o=} {ll=} {s=}.  Full error {exp}")
                    os.unlink(out)
