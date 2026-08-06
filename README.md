# GUI

## Installation
Run the installer `Q:\Hydro\rec2cdf\rec2cdfsetup.exe` (or if not in
Christchurch go to `Q:\(Other Sites)\Christchurch\Hydro\rec2cdf`)

## Run

You can run the GUI called rec2cdfgui.exe that should be installed with the above
installer.

## Other installation methods

If you have python installed you can install the requirements.pip with pip and
run the command line program [bin/rec2cdf.py](bin/rec2cdf.py) or the GUI
[bin/rec2cdf.pyw](bin/rec2cdfgui.pyw).

## GUI build instructions

I use pyinstaller to make a single executable (or a folder with an executable in
it).  Then inno to turn this into a MSI installer.

To make the pyinstaller outputs as small as possible it helps to use a virtual
environment for python.  I think pyinstaller is supposed to only include
necessary libraries, but I've found that it puts in way more than is necessary.
Using a virtual environment avoids that.

The GUI install used to be tricky because pyinstaller and geopandas/shapely/fiona/gdal
installed via pip and
[cgohlke](https://github.com/cgohlke/geospatial-wheels/releases) did not play
very well together.  I had to use cgohlke on windows othewise you are
trying to install compilers and gdal libs.  Unfortunately the resulting binary
that pyinstaller built (in 2022) tried to open up a non-existant directory
called Shapely.Libs, so I switched to conda, but then conda started having
other problems in 2023 (which I can't remember now), so I switched back to pip
and virtual environments.  I had to hand edit two files
`~/Documents/venvs/rec2cdf/Lib/site-packages/geopandas/_compat.py` and
`~/Documents/venvs/rec2cdf/Lib/site-packages/_pyinstaller_hooks_contrib/hooks/stdhooks/hook-shapely.py`.
But as of Sep 2024 this has all changed and we don't need cgohlke libs or muck
with anything!

1. Download and install Python 3.12

2. Make a virtual environment and install packages
    ```
    python -m venv ~/Documents/venvs/rec2cdf
    . ~/Documents/venvs/rec2cdf/Scripts/activate
    python -m pip install --upgrade pip
    pip install -r requirements.pip
    ```

3. To build dist/rec2cdf/rec2cdf.exe run
   ```
   pyinstaller -y rec2cdf.spec
   ```

4. If you want to rebuild the rec2cdf.spec file run
   ```
   pyinstaller -y bin/rec2cdfgui.pyw --onedir --noconsole --hidden-import cftime --hidden-import netCDF4 --hidden-import telnetlib --add-data="bin/rec2cdf.py;." --add-data="bin/smap.py;." --add-data="bin/map.html;." --add-data="bin/version.txt;." --add-data="bin/help.html;." --icon="etc/rec2cdf.ico" --add-data="etc/rec2cdf.ico;."
   ```
   Using --onefile makes a single executable rec2cdf.exe which is neat and tidy
   but it is slower to run than having the entire directory, so --onedir is the
   way to go.  We use inno anyway to turn that directory into a MSI installer anyway.
 
5. The directory `dist/rec2cdf` can be turned into a proper MSI Windows Setup
   file using inno and the setup file [inno.iss](inno.iss)


# CLI

## Debian

To get bin/rec2cdf.py to run you need (amongst other things) these three
python packages: netcdf4, psycopg2, and pathlib2.  On debian you can
install like this:

`sudo apt-get install python-netcdf4 python-psycopg2 python-pathlib2`

## HPCF

But a better way is to make a virtual environment, which is what I have
done on Maui.

```
module load Python/3.8.2
python -m venv /nesi/project/niwa03440/wilkinsmc/venv/rec2cdf
. /nesi/project/niwa03440/wilkinsmc/venv/rec2cdf/bin/activate
python -m pip install --upgrade pip
pip install netcdf4 psycopg2-binary pathlib2
```

So to run just
```
module load Python/3.8.2
. /nesi/project/niwa03440/wilkinsmc/venv/rec2cdf/bin/activate
export REC2CDFPW=blahblah
./bin/rec2cdf.py -bl -e 10000000 --outfile=/nesi/project/niwa03440/spatials/spatial_9000000_B_L_rec2_strahler1.nc 9000000


## Hydrodesk

To incorporate with hydrodesk do the following:
* Copy `bin/rec2cdf.py`, `bin/grid2cdf.py`, and
  `bin/netCDF_Methods.py` to a directory that the webservice can
  access, such as `/hydrodesk/rec2cdf/`
* Tell the hydrodesk webservice where rec2cdf.py lives using the admin
  web interface.

# Database setup

Ideally we would have the rec databases living on a central postgresql
database somewhere.  In lieu of that we have them living locally, this
is how I set my postgresql database up on debian using backup dumps
from Ude:

1. `sudo apt-get install postgresql postgresql-contrib python3-psycopg2`
2. `sudo -u postgres createuser --createdb --pwprompt spatialuser`
    The user password should match the `dbpasswd` variable in `../src/rec2cdf.py`
3. `sudo -u postgres createdb --owner=spatialuser rec1`
4. `sudo -u postgres createdb --owner=spatialuser rec2`
5. `sudo -u postgres psql rec1 -c "create extension adminpack;"`
6. `sudo -u postgres psql rec2 -c "create extension adminpack;"`
7. `sudo -u postgres pg_restore --host=localhost --dbname=rec1 --verbose --username=spatialuser  /tmp/rec1bkp.tar`
8. `sudo -u postgres pg_restore --host=localhost --dbname=rec2 --verbose --username=spatialuser  /tmp/rec2bkp.tar`

# Providence and maintenance guidance

This code used to live at https://git.niwa.co.nz/nzwam/rec2cdf, but we can't run CI/CD there.

See the [maintenance](maintenance.md) file for how to update rec2cdf or
supporting geofabric.

