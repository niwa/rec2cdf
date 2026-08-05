# Make shapefile from spatials

This makes a network gpkg file for the network used by tn_nzcsm_national. The
network info is obtained directly from the spatial files and the rec1 database
on wellhydrodb.

# Install

Install virtual environment:

*  Maui
   ```
   module purge
   module load NeSI
   module load Anaconda3/2019.07-gimkl-2018b
   mkdir -p ~/scratch/venvs
   python -m venv ~/scratch/venvs/make_network_maui
   . ~/scratch/venvs/make_network_maui/bin/activate
   python -m pip install --upgrade pip
   pip install -r requirements.pip
   ```

* Mahuika
   ```
   module purge
   module load NeSI
   module load Anaconda3/2021.05-gimkl-2020a
   mkdir -p ~/scratch/venvs
   python -m venv ~/scratch/venvs/make_network_mahuika
   . ~/scratch/venvs/make_network_mahuika/bin/activate
   python -m pip install --upgrade pip
   pip install -r requirements.pip
   ```

NB: this script will not run from Mahuika since it requires access to
wellhydrodb.

# Run

`python make_network.py spatial_rec_*_strahler3.nc out.gpkg`

# Info about spatial file fields

The reason we need wellhydrodb is there is no geometry info in the
spatial file, and also there is no connectivity (down or up) for every
single reach, only from aggregate reach to aggregate reah.  This means
we cannot trace our way *through* the aggregate reach.  And this is what
is needed to form the line for the aggregate.  Anyway, here is a summary
of some of the info I found in the spatial files:

* Non-aggregates (ie for every reach):

    * `rchid_noagg`: 1d, element i is ith reach ID
    * `rchid_agg`: 1d, element i gives the ith reach's aggregate reach ID
      (you can get this info in a more natural way from nonaggrch_rchid)

* Aggregates (ie just for aggregate reaches):

    * `uprch_rchid`: 2d, row i gives the upstream rchid's for aggregate i
    * `nonaggrch_rchid`: 2d, row i gives the rchid's in aggregate i
    * `dsrch_rchid`: 1d, element i gives the downstream rchid for aggregate i
    * `rchid`: 1d, element i is reach id for aggregate i

