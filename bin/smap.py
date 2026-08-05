# -*- coding: utf-8 -*-
"""The slippery map

Classes
-------

class Interceptor(QWebEngineUrlRequestInterceptor):

class Backend(QObject):
    Communication between the webengine and map

class SMap(QObject):
    Main slippery map object containing the webengine

"""

import sys
import pathlib
import tempfile
import numpy as np
import geopandas as gp
import shapely
import pandas as pd
import json
from PyQt5.QtCore import QUrl, QObject, pyqtSlot, pyqtSignal, QThread
from PyQt5.QtWidgets import QMessageBox
from PyQt5.QtWebEngineCore import QWebEngineUrlRequestInterceptor
from PyQt5.QtWebEngineWidgets import QWebEngineView
from PyQt5 import QtWebChannel


class Interceptor(QWebEngineUrlRequestInterceptor):
    def interceptRequest(self, info):
        info.setHttpHeader("Accept-Language", "en-US,en;q=0.9,es;q=.8,de;q=0.7")


class Backend(QObject):
    left_click_at = pyqtSignal(float, float)
    right_click_at = pyqtSignal(float, float)
    poly_selection = pyqtSignal(str)
    loaded_sig = pyqtSignal()

    @pyqtSlot(float, float)
    def left_click(self, x, y):
        self.left_click_at.emit(x, y)

    @pyqtSlot(float, float)
    def right_click(self, x, y):
        self.right_click_at.emit(x, y)

    @pyqtSlot()
    def loaded_slot(self):
        self.loaded_sig.emit()

    @pyqtSlot(str)
    def poly_created(self, x):
        # print(f"Poly created {x}", flush=True)
        self.poly_selection.emit(x)



class SMap(QObject):
    # we emit this signal when the reach id is changed by a left click
    rids_toggle = pyqtSignal(int, str)
    # signal to add rids by polygon select [(r0, g0), (r1, g1), ...]
    rids_add = pyqtSignal(list)
    # we emit this when we want to clear all rids
    rids_clear = pyqtSignal()
    # emit this when truncate reach clicked on (rid, geom)
    truncates_toggle = pyqtSignal(int, str)
    truncates_add = pyqtSignal(list)
    # emit this when we want to clear all truncated reaches
    truncates_clear = pyqtSignal()

    def __init__(self, parent=None, dn=2, order=1, blakes=True, bsites=True, db=None):
        super(QObject, self).__init__(parent)

        self.browser = QWebEngineView()

        backend = Backend(self)
        channel = QtWebChannel.QWebChannel(self)
        channel.registerObject("backend", backend)
        self.browser.page().setWebChannel(channel)
        backend.left_click_at.connect(self.display_closest_reach)
        backend.right_click_at.connect(
            lambda x, y: self.display_closest_reach(x, y, True)
        )
        backend.loaded_sig.connect(self.display_sites)
        backend.poly_selection.connect(self.poly_selection)

        self.browser.page().profile().setUrlRequestInterceptor(Interceptor())

        if getattr(sys, "frozen", False):
            fname = pathlib.Path(sys._MEIPASS) / "map.html"
        else:
            fname = pathlib.Path(sys.argv[0]).resolve().parent / "map.html"
        self.browser.load(QUrl.fromLocalFile(str(fname)))

        # we need to keep track of these for tracing
        self.dn = dn
        self.order = order
        self.blakes = blakes
        self.bsites = bsites

        # for tracing
        self.db = db

        # upstream trace and watersheds dataframes, and a cache of them
        self.tracedf = []
        self.tracecache = TraceCache()

        # it is possible to start multiple threads tracing, keep track in here
        self.threads = []
        self.workers = {}

    def clear_trace_cache(self):
        self.tracecache.clear()

    def display_sites(self):
        """Add the site data to map."""

        if not self.db:
            return

        self.db.connect()
        df = gp.GeoDataFrame.from_postgis("select * from sites", self.db._con)
        # can't use parse_dates in previous since different timezones (NZST and NZDT)
        df.start = pd.to_datetime(df.start, utc=True)
        df.end = pd.to_datetime(df.end, utc=True)

        # for displaying
        df.start = df.start.dt.strftime("%Y-%m-%d").fillna("")
        df.end = df.end.dt.strftime("%Y-%m-%d").fillna("")
        df["popupContent"] = (
            "Site: "
            + df.site.astype(str)
            + "<br>Var: "
            + df["var"]
            + "<br>Name: "
            + df.name
            + "<br>Reach IDs: "
            + df.rid_dn1.astype(str)
            + ", "
            + df["rid_dn2.3"].astype(str)
            + ", "
            + df["rid_dn2.5"].astype(str)
            + ", "
            + df.rid_dn3.astype(str)
            + "<br>Start: "
            + df.start
            + "<br>End: "
            + df.end
        )

        self.browser.page().runJavaScript(
            f"siterainlayer.addData({df[df['var'] == 'rain'].to_json()});"
            f"siteflowlayer.addData({df[df['var'] == 'flow'].to_json()});"
            f"sitesmlayer.addData({df[df['var'] == 'sm'].to_json()});"
            f"sitetemplayer.addData({df[df['var'] == 'temp'].to_json()});"
        )

    def set_dbcon(self, db):
        """Set the DB connection we can use for river network tracing."""
        self.db = db

    def no_db(self, msg):
        """Show error about no database connection."""

        mb = QMessageBox()
        mb.setIcon(QMessageBox.Critical)
        mb.setText("Error")
        mb.setInformativeText(
            msg + "\n\nGo to File->Database to set up your database connection"
        )
        mb.setWindowTitle("Error")
        mb.exec_()

    @pyqtSlot(str)
    def dn_changed(self, dn):
        """Tell the map to get correct DN tiles."""
        self.dn = int(dn)
        self.browser.page().runJavaScript(
            f"update_dnvtiles({self.dn}, {self.order}, {'true' if self.blakes else 'false'}, {'true' if self.bsites else 'false'}) ; clear_geom()"
        )
        self.rids_clear.emit()
        self.truncates_clear.emit()

    @pyqtSlot(str)
    def order_changed(self, ord):
        """So we know what the strahler order is for tracing."""
        self.order = int(ord)
        self.browser.page().runJavaScript(
            f"update_dnvtiles({self.dn}, {self.order}, {'true' if self.blakes else 'false'}, {'true' if self.bsites else 'false'}) ; clear_geom()"
        )
        self.rids_clear.emit()
        self.truncates_clear.emit()

    @pyqtSlot(int)
    def blakes_changed(self, blakes):
        """So we know what the strahler order is for tracing."""
        self.blakes = True if blakes else False
        self.browser.page().runJavaScript(
            f"update_dnvtiles({self.dn}, {self.order}, {'true' if self.blakes else 'false'}, {'true' if self.bsites else 'false'}) ; clear_geom()"
        )
        self.rids_clear.emit()
        self.truncates_clear.emit()

    @pyqtSlot(int)
    def bsites_changed(self, bsites):
        """So we know what the strahler order is for tracing."""
        self.bsites = True if bsites else False
        self.browser.page().runJavaScript(
            f"update_dnvtiles({self.dn}, {self.order}, {'true' if self.blakes else 'false'}, {'true' if self.bsites else 'false'}) ; clear_geom()"
        )
        self.rids_clear.emit()
        self.truncates_clear.emit()

    def rat_dbname(self) -> str:
        """Return the aggregated database for this config"""

        if self.order == 1:
            return f"rat_dnv{self.dn}"
        return f"rat_dnv{self.dn}_order{self.order}_lakes{self.blakes}_sites{self.bsites}".lower()

    def info_for(self, rid: int):
        """Return geom for reach in potentially aggregated network

        Parameters
        ----------
        rid: int
            Reach ID

        Returns
        -------
        str:
            geom if rid exists in current network, else None
        """

        if not self.db:
            self.no_db("Cannot find reach ID since no access to REC database")
            return

        rdb = self.rat_dbname()

        s = f"""
            SELECT ST_AsGeoJSON(geom)
            FROM {rdb}
            WHERE nzreach = {rid}
            LIMIT 1;
        """
        try:
            cur = self.db.execute(s)
        except Exception as exp:
            self.no_db(f"Cannot find {rid} in this network.  Full error is:\n{exp}")
            return
        g = cur.fetchone()
        if g and len(g) == 1:
            return g[0]
        self.no_db(f"Cannot find {rid} in this network")

    def closest_rid(self, x, y):
        """Return closest reach in potentially aggregated network

        Parameters
        ----------
        x: float
            x coordinate in srid 4326, so the longitude

        y: float
            y coordinate in srdi 4326, so the latitude

        Returns
        -------
        tuple:
            (rid, geom).
            rid is reach ID closest to (x, y), or None if there aren't any
        """

        if not self.db:
            self.no_db("Cannot find reach ID since no access to REC database")
            return

        rdb = self.rat_dbname()

        # get closest
        s = f"""
            SELECT nzreach, ST_AsGeoJSON(geom),
            ST_Distance(geom, ST_SetSRID(ST_MakePoint({x}, {y}), 4326)) as dist
            FROM {rdb}
            WHERE ST_DWithin(
                geom, ST_SetSRID(ST_MakePoint({x}, {y}), 4326), 0.01
            )
            ORDER BY dist ASC
            LIMIT 1;
        """
        try:
            cur = self.db.execute(s)
        except Exception as exp:
            self.no_db(
                "Cannot query database, possibly because it doesn't "
                "have the correct tables set up for tracing.  Full "
                f"error is:\n{exp}"
            )
            return
        return cur.fetchone()

    #    def rid_to_aggrid(self, rid, geom):
    #        """Return the aggregate rid and geom for given rid.
    #
    #        Parameters
    #        ----------
    #        rid: int
    #            Reach ID
    #
    #        geom: str, geojson
    #            The geometry of rid
    #
    #        Returns
    #        -------
    #        tuple:
    #            (aggrid, geom), where aggrid is aggregate reach ID int, and geom is
    #            the geojson string of the geometry of the aggregate reach
    #        """
    #
    #        if self.order == 1:
    #            return (rid, geom)
    #
    #        # trace downstream in nonaggregated network until we find a reach in aggregated network
    #        s = f"""
    #            WITH RECURSIVE tree AS (
    #                SELECT nzreach, ST_AsGeoJSON(geom), down
    #                FROM rat_dnv{self.dn}
    #                WHERE nzreach = {rid}
    #
    #                UNION ALL
    #
    #                SELECT tab.nzreach, ST_AsGeoJSON(geom) as geom, tab.down
    #                FROM rat_dnv{self.dn} AS tab
    #                JOIN tree ON tab.nzreach = tree.down
    #
    #                WHERE NOT EXISTS (
    #                    SELECT FROM {self.rat_dbname()} WHERE nzreach = tree.nzreach
    #                )
    #            )
    #            SELECT * FROM tree;
    #        """
    #        try:
    #            cur = self.db.execute(s)
    #        except Exception as exp:
    #            self.no_db(
    #                "Cannot query database, possibly because it doesn't "
    #                "have the correct tables set up for tracing.  Full "
    #                f"error is:\n{exp}"
    #            )
    #            return
    #        if not (ret := cur.fetchall()):
    #            return
    #
    #        return ret[-1][:2]

    @pyqtSlot(float, float)
    def display_closest_reach(self, x, y, truncate=False):
        """Display closest agg reach, catchment or truncate reach

        Adds the geometry of the reach to the slippery map

        Parameters
        ----------
        x: float
            x coordinate in srid 4326, so the longitude

        y: float
            y coordinate in srdi 4326, so the latitude

        truncate: bool
            Truncating the network at (x, y) instead of starting catchment

        Returns
        -------
        None
        """

        if rg := self.closest_rid(x, y):
            rid, geom = rg[:2]
        else:
            return

        # if we had a trace, remove since probably won't make sense
        if self.tracedf != []:
            self.browser.page().runJavaScript(
                "tracelayer.clearLayers(); wshedlayer.clearLayers()"
            )
            self.tracedf = []

        # map gets updated by a slot display_rids or display_truncates since we
        # don't keep track of list here
        if truncate:
            self.truncates_toggle.emit(rid, str(geom))
        else:
            self.rids_toggle.emit(rid, str(geom))

    @pyqtSlot(list)
    def display_rids(self, geoms: list):
        self.browser.page().runJavaScript("sellayer.clearLayers()")
        for g in geoms:
            self.browser.page().runJavaScript(f"sellayer.addData({g})")

    @pyqtSlot(list)
    def display_truncates(self, geoms: list):
        self.browser.page().runJavaScript("truncatelayer.clearLayers()")
        for g in geoms:
            self.browser.page().runJavaScript(f"truncatelayer.addData({g})")

    @pyqtSlot(int)
    def trace(self, rids: list, truncates: list):
        """Trace from rid

        Adds the geometry of the trace and watersheds to the slippery map

        Parameters
        ----------
        rids: list
            A list of reaches to trace from

        truncates: list
            A list of reach IDs to stop at

        Returns
        -------
        None
        """

        self.tracedf = []
        self.browser.page().runJavaScript(
            "tracelayer.clearLayers() ; wshedlayer.clearLayers() ;"
        )
        for rid in rids:
            # if cached, just display it
            if (
                t := self.tracecache[
                    (self.dn, rid, self.order, self.blakes, self.bsites, truncates)
                ]
            ) is not None:
                self.tracedf.append(t)
                self.display_trace(t)
                continue

            # this runs the trace or aggregate
            self.browser.page().runJavaScript("waiting()")
            thd = QThread()
            self.threads.append(thd)
            worker = Worker(
                self.db,
                self.browser,
                self.dn,
                rid,
                self.order,
                self.blakes,
                self.bsites,
                truncates,
            )
            # store the worker in this dict so we can get it back in the slot
            self.workers[f"{self.dn}{rid}{self.order}{self.blakes}{self.bsites}{''.join(map(str, truncates))}"] = worker
            worker.moveToThread(thd)
            worker.error.connect(self.display_error)
            thd.started.connect(worker.run)
            worker.finished.connect(thd.quit)
            worker.finished.connect(worker.deleteLater)
            worker.trace_ready.connect(self.save_trace_and_display)
            thd.finished.connect(thd.deleteLater)
            thd.finished.connect(lambda: self.browser.page().runJavaScript("ready()"))
            thd.start()

   
    @pyqtSlot(str)
    def save_trace_and_display(self, w):
        """Save the trace that is in the worker given by string w"""

        w = self.workers[w]
        if w.df is None:
            return

        self.tracecache[
            (w.dn, w.rid, w.order, w.blakes, w.bsites, w.truncates)
        ] = w.df
        self.tracedf.append(w.df)
        self.display_trace(w.df)


    def display_trace(self, df):
        """Display the given trace

        Parameters
        ----------
        df: gpd.GeoDataFrame
            Should have line and wshed columns.
        """

        # possibly no trace if user is repeatly clicking on large traces
        if df is None:
            return

        # runJavaScript crashes if the string (ups/wsheds) is too long. This
        # happened for dn2 rid 13212900, df has about 24k lines. So do this in
        # chunks, 1000 rows at a time appears to be fine. Grouping by a list
        # length df accomplishes this:
        for k, g in df.groupby(np.arange(len(df)) // 1000):
            ups = gp.GeoSeries(g.geom).to_json()
            wsheds = gp.GeoSeries(g.watershed).to_json()
            self.browser.page().runJavaScript(
                f"tracelayer.addData({ups}) ; wshedlayer.addData({wsheds}) ;"
            )

    @pyqtSlot(str)
    def display_error(self, msg):
        self.no_db(msg)

    @pyqtSlot(str)
    def poly_selection(self, x):
        try:
            x = json.loads(x)[0]
        except Exception as exp:
            self.display_error(f"Bad polygon {exp}")
            return

        poly = shapely.geometry.Polygon([(p['lng'], p['lat']) for p in x])
        # print(poly.wkt, flush=True)

        if not self.db:
            self.no_db("Cannot find reachs since no access to DNV database")
            return
        rdb = self.rat_dbname()

        s = f"""
            CREATE TEMP TABLE inside AS
            SELECT nzreach, down, geom
            FROM {rdb}
            WHERE ST_Contains(
                ST_SetSRID(
                    ST_PolygonFromText('{poly.wkt}'),
                    4326
                ),
                geom
            );

            SELECT nzreach, ST_AsGeoJSON(geom), 'rids' AS type
            FROM inside BLAH
            WHERE down IS null OR
            NOT EXISTS (SELECT FROM inside WHERE nzreach = BLAH.down)

            UNION

            SELECT nzreach, ST_AsGeoJSON(geom), 'truncates' AS type
            FROM {rdb} AS outside
            WHERE
                NOT EXISTS (SELECT FROM inside WHERE nzreach = outside.nzreach) AND
                EXISTS (SELECT FROM inside WHERE nzreach = outside.down);
        """
        try:
            cur = self.db.execute(s)
        except Exception as exp:
            self.no_db(f"Cannot find any reaches.  Full error is:\n{exp}")
            return 
        ret = cur.fetchall()

        rids = [(r, g) for r, g, t in ret if t == 'rids']
        truncates = [(r, g) for r, g, t in ret if t == 'truncates']
        self.rids_add.emit(rids)
        self.truncates_add.emit(truncates)



class TraceCache:
    """A memory and disk cache that holds traces.

    Because windows has short path lengths (256 or so), we need to hash any keys (since they will be filenames) to make them shorter

    """

    def __init__(self):
        self.dir = pathlib.Path(tempfile.gettempdir())
        self.memcache = {}

    def __sluggify(self, key):
        key = ("-".join(map(str, k)) if type(k) is list else str(k) for k in key)
        key = "_".join(map(str, key))
        return str(hash(key))

    def __getitem__(self, key):
        """Return in memory, or from disk.

        Parameters
        ----------
        key: tuple
            Probably (dn, rid, order, blakes, bsites, truncates)
            Any element in the tuple that is a list gets joined by -
        """

        key = self.__sluggify(key)

        # try in memory
        if key in self.memcache:
            return self.memcache[key]
        # try from disk
        fname = (self.dir / key).with_suffix(".pickle")
        if fname.exists():
            ret = self.memcache[key] = pd.read_pickle(fname)
            return ret
        return None

    def __setitem__(self, key, value):
        """Set the memcache and the on disk cache."""
        key = self.__sluggify(key)

        self.memcache[key] = value
        fname = (self.dir / key).with_suffix(".pickle")
        value.to_pickle(fname)

    def clear(self):
        self.memcache.clear()
        for p in self.dir.glob("*.pickle"):
            try:
                p.unlink()
            except Exception:
                pass


class Worker(QObject):
    """Do the trace or aggregate"""

    finished = pyqtSignal()
    trace_ready = pyqtSignal(str)
    error = pyqtSignal(str)

    def __init__(
        self, db, browser, dn, rid, order, break_lakes, break_sites, truncates
    ):
        super().__init__()
        self.db = db
        self.browser = browser
        self.dn = dn
        self.rid = rid
        self.order = order
        self.blakes = break_lakes
        self.bsites = break_sites
        self.truncates = truncates
        self.df = None

    def rat_dbname(self) -> str:
        """Return the aggregated database for this config"""

        if self.order == 1:
            return f"rat_dnv{self.dn}"
        return f"rat_dnv{self.dn}_order{self.order}_lakes{self.blakes}_sites{self.bsites}".lower()

    def run(self):
        # trace if order 1, else we need to aggregate
        df = self.trace(self.rid, self.truncates)
        if df:
            df = gp.GeoDataFrame(
                df,
                columns=[
                    "nzreach",
                    "down",
                    "order",
                    "lake",
                    "site",
                    "geom",
                    "watershed",
                ],
            )
            # geoms are memory views, need to convert to bytes first.
            df.geom = df.geom.apply(bytes).apply(shapely.wkb.loads)
            df.watershed = df.watershed.apply(bytes).apply(shapely.wkb.loads)
            df = df.set_geometry("geom").set_crs(4326)
            df = df.set_geometry("watershed").set_crs(4326)

            self.df = df

            self.trace_ready.emit(f"{self.dn}{self.rid}{self.order}{self.blakes}{self.bsites}{''.join(map(str, self.truncates))}")

        self.finished.emit()

    def trace(self, rid, truncates):
        """Trace upstream from rid returning upstream and watersheds.

        Parameters
        ----------
        rid: int
            Starting reach

        truncates: list
            A list of reaches to stop at

        Returns
        -------
        tuple:
            (geom, watershed), where both are as geojson, and are for the
            entire trace.
            geom is a multilinestring
            watershed is geometry collection of multipolygons
        """

        # if truncates need to stop tracing
        cond = (
            (f" AND tab.nzreach NOT IN ({','.join(map(str, truncates))})")
            if truncates
            else ""
        )

        d = self.rat_dbname()
        s = f"""
            WITH RECURSIVE tree AS (
                SELECT nzreach, down, "order", lake, site, geom, watershed
                FROM {d}
                WHERE nzreach={rid}

            UNION ALL

                SELECT tab.nzreach, tab.down, tab."order", tab.lake,
                    tab.site, tab.geom, tab.watershed
                FROM {d} as tab
                JOIN tree ON tab.down = tree.nzreach{cond}
            )
            SELECT nzreach, down, "order", lake, site,
                ST_AsEWKB(geom), ST_AsEWKB(watershed)
            FROM tree;
        """
        try:
            cur = self.db.execute(s)
        except Exception as exp:
            self.error.emit(
                "Cannot query database, possibly because it doesn't "
                "have the correct tables set up for tracing.  Full "
                f"error is:\n{exp}"
            )
            return
        return cur.fetchall()
