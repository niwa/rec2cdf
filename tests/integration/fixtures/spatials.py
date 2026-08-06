import pathlib
import pytest
import xarray as xr

basedir = "tests/integration/data"


@pytest.fixture
def dn2s1small():
    """
    import pathlib
    basedir = "tests/integration/data"
    out = (
      ".." / pathlib.Path(basedir) / f"{14194105}_dn2_order1_lakes_sites.nc"
    )
    print(
      f"python3 rec2cdf.py -ls -o 1 --outfile={out} "
      "14194105 --dbname dn25"
    )
    """
    s = pathlib.Path(basedir) / "14194105_dn2_order1_lakes_sites.nc"
    return xr.open_dataset(s)


@pytest.fixture
def truncated():
    """
    import pathlib
    basedir = "tests/integration/data"
    out = (
      ".." / pathlib.Path(basedir) / f"{13146864}_truncated.nc"
    )
    print(
      f"python3 rec2cdf.py -ls -o 2 --outfile={out} "
      "13146864 --dbname dn25 --truncates 13145227,13145209"
    )
    """
    s = pathlib.Path(basedir) / "13146864_truncated.nc"
    return xr.open_dataset(s)


@pytest.fixture
def lotsalakes():
    # this is from dn2 13172090
    # to generate all these fixtures run this python to generate a bunch of
    # commands
    """
    import pathlib
    basedir = "tests/integration/data"
    for d in (2,):
      for o in (1, 2, 3):
        for ll in (True, False):
          for s in (True, False):
            out = (
              ".." / pathlib.Path(basedir) / f"{13172090}_dn{d}_order{o}_"
              f"{'lakes' if ll else 'nolakes'}_"
              f"{'sites' if s else 'nosites'}.nc"
            )
            print(
              f"python3 rec2cdf.py {'-l' if ll else ''} "
              f"{'-s' if s else ''} -o {o} --outfile={out} "
              "13172090 --dbname dn25"
            )
    """
    return {
        f"{d}{o}{ll}{s}": xr.open_dataset(
            pathlib.Path(basedir) / f"{13172090}_dn{d}_order{o}_"
            f"{'lakes' if ll else 'nolakes'}_"
            f"{'sites' if s else 'nosites'}.nc"
        )
        for d in (2,)
        for o in (1, 2, 3)
        for ll in (True, False)
        for s in (True, False)
    }


@pytest.fixture
def sigabovenonsig():
    # this is from dn2 13173665 order 3, broken at lakes and sites.  we have
    # significant reaches above non significant due to the lakes/sites and high
    # aggregation order.  this is to test connectivity and the llength stuff,
    # which is based on the significant reaches in an aggregate
    """
    import pathlib
    basedir = "tests/integration/data"
    for d in (2,):
      for o in (1, 2, 3,):
        for ll in (True, ):
          for s in (True, ):
            out = (
              ".." / pathlib.Path(basedir) / f"{13173665}_dn{d}_order{o}_"
              f"{'lakes' if ll else 'nolakes'}_"
              f"{'sites' if s else 'nosites'}.nc"
            )
            print(
              f"python3 rec2cdf.py {'-l' if ll else ''} "
              f"{'-s' if s else ''} -o {o} --outfile={out} "
              "13173665 --dbname dn25"
            )
    """
    return {
        f"{d}{o}{ll}{s}": xr.open_dataset(
            pathlib.Path(basedir) / f"{13173665}_dn{d}_order{o}_"
            f"{'lakes' if ll else 'nolakes'}_"
            f"{'sites' if s else 'nosites'}.nc"
        )
        for d in (2,)
        for o in (1, 2, 3)
        for ll in (True,)
        for s in (True,)
    }
