#!/usr/bin/env python

import os
import sys
import psycopg2
import socket
import re
import pathlib
import configparser
import keyring
import logging
import atexit
import platformdirs
import requests
from packaging import version
import pandas as pd

# this is so we can view exceptions on the windows compiled exe
# import traceback

from rec2cdf import setup_logging, gen_spatial
from db import DB

from PyQt5.QtWidgets import (
    QApplication,
    QHBoxLayout,
    QFormLayout,
    QWidget,
    QComboBox,
    QLineEdit,
    QCheckBox,
    QMainWindow,
    QMenu,
    QAction,
    QVBoxLayout,
    QDialog,
    QDialogButtonBox,
    QTextEdit,
    QMessageBox,
    QFileDialog,
    QPushButton,
    QPlainTextEdit,
    QSplitter,
)
from PyQt5.QtCore import Qt, pyqtSignal, QObject, QThread, pyqtSlot
from PyQt5.QtGui import QIcon

from smap import SMap

# this for window gui crashes
#def my_except_hook(ty, value, tb):
#    with open(pathlib.Path.home() / "rec2cdf_crash.txt", "w") as fh:
#        traceback.print_exception(ty, value, tb, file=fh)
#sys.excepthook = my_except_hook


def rid_to_db(rid):
    """Return the dn3 database for this range of reaches

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


class Watcher(QObject):
    """Tail logfile and print lines in statusbar."""

    # emit this signal when there is something to print
    display = pyqtSignal(str)

    # when finished watching the file
    finished = pyqtSignal()

    def __init__(self, fname):
        super().__init__()
        self.stop = False
        self.fname = fname

    def run(self):
        # busy wait for the log file to appear
        while not os.path.exists(self.fname):
            pass

        try:
            f = open(self.fname)
        except Exception:
            self.display.emit(f"Could not open log file {self.fname}")
            self.finished.emit()
            return

        while not self.stop:
            if line := f.readline():
                self.display.emit(line.rstrip())

        f.close()
        self.finished.emit()

    def finish(self):
        self.stop = True


class Worker(QObject):
    """Run rec2cdf"""

    finished = pyqtSignal()

    def __init__(
        self,
        dbname,
        dbhost,
        dbuser,
        dbpasswd,
        logfile,
        outfile,
        rids,
        break_network,
        include_lakes,
        regional,
        order,
        version,
        truncate,
    ):
        super().__init__()
        self.dbname = dbname
        self.dbhost = dbhost
        self.dbuser = dbuser
        self.dbpasswd = dbpasswd
        self.logfile = pathlib.Path(logfile)
        self.outfile = pathlib.Path(outfile)
        self.rids = rids
        self.break_network = break_network
        self.include_lakes = include_lakes
        self.regional = regional
        self.order = order
        self.version = version
        self.truncates = truncate

    def run(self):
        fhand = setup_logging(self.outfile, self.logfile, "INFO")

        # connect
        try:
            con = psycopg2.connect(
                host=self.dbhost,
                user=self.dbuser,
                password=self.dbpasswd,
                database=self.dbname,
            )
        except Exception as exp:
            logging.error(
                f"Cannot connect to database {self.dbhost}, error was\n{exp}\n\n"
                "Go to File->Database to set up your database connection"
            )
            fhand.close()
            self.finished.emit()
            return

        # run
        rids = gen_spatial(
            self.outfile,
            self.rids,
            con,
            self.order,
            self.include_lakes,
            self.break_network,
            self.regional,
            self.truncates,
        )
        if not rids:
            logging.error(f"Something went wrong, removing incomplete {self.outfile}")
            self.outfile.unlink(missing_ok=True)

        fhand.close()
        self.finished.emit()


class ClickableLineEdit(QLineEdit):
    clicked = pyqtSignal()

    def mousePressEvent(self, e):
        if e.button() == Qt.LeftButton:
            self.clicked.emit()
        else:
            super().mousePressEvent(e)


class TextEditSized(QPlainTextEdit):
    """TextEdit with sizeHint."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setReadOnly(True)

    def sizeHint(self):
        s = super().sizeHint()
        s.setHeight(50)
        return s


class Window(QMainWindow):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Rec2CDF")

        # icon
        if getattr(sys, "frozen", False):
            fname = pathlib.Path(sys._MEIPASS) / "rec2cdf.ico"
        else:
            me = pathlib.Path(sys.argv[0]).resolve()
            fname = me.parent.parent / "etc" / "rec2cdf.ico"
        # on linux we need a ppm/pgm file, not a windows ico, just ignore
        try:
            self.setWindowIcon(QIcon(str(fname)))
        except Exception:
            pass

        # splitter contains hlayout and text area at bottom
        splitter = QSplitter(Qt.Vertical)

        # hlayout contains the vlayout on the left and smap on the right
        hlayout = QHBoxLayout()

        # vlayout contains the form layout with Go button at the bottom
        vlayout = QVBoxLayout()
        flayout = QFormLayout()

        # the slippery map
        self.smap = smap = SMap(parent=self)

        self.dn = dn = QComboBox()
        dn.setToolTip("Digital network version")
        dn.addItems(["1", "2", "3"])
        dn.setCurrentIndex(1)
        flayout.addRow("DN:", dn)
        dn.currentTextChanged.connect(smap.dn_changed)

        self.order = order = QComboBox()
        order.setToolTip("Strahler order")
        order.addItems(map(str, range(1, 10)))
        flayout.addRow("Order:", order)
        order.currentTextChanged.connect(smap.order_changed)

        self.blakes = blakes = QCheckBox("")
        blakes.setToolTip("Break the network at lakes")
        blakes.setChecked(True)
        flayout.addRow("Break at lakes:", blakes)
        blakes.stateChanged.connect(smap.blakes_changed)

        self.bsites = bsites = QCheckBox("")
        bsites.setToolTip("Break the network at sites/stations")
        bsites.setChecked(True)
        flayout.addRow("Break at sites:", bsites)
        bsites.stateChanged.connect(smap.bsites_changed)

        self.regional = regional = QCheckBox("")
        regional.setToolTip("Do entire region reach is in")
        regional.setChecked(False)
        flayout.addRow("Regional:", regional)

        self.ridstr = ridstr = QLineEdit()
        ridstr.setToolTip("The reach IDs of the catchment")
        flayout.addRow("Reach IDs:", ridstr)
        ridstr.editingFinished.connect(self.ridstr_edited)
        smap.rids_toggle.connect(self.rids_toggle)
        smap.rids_add.connect(self.rids_add)
        smap.rids_clear.connect(self.rids_clear)
        self.rids = {}  # maps rid to geom

        self.truncatestr = truncatestr = QLineEdit()
        truncatestr.setToolTip("The reach IDs to truncate catchment")
        flayout.addRow("Truncate IDs:", truncatestr)
        truncatestr.editingFinished.connect(self.truncatestr_edited)
        smap.truncates_toggle.connect(self.truncates_toggle)
        smap.truncates_add.connect(self.truncates_add)
        smap.truncates_clear.connect(self.truncates_clear)
        self.truncates = {}  # maps truncate to geom

        self.spatial = spatial = ClickableLineEdit()
        spatial.setToolTip("The spatial file name")
        flayout.addRow("Spatial file:", spatial)
        spatial.clicked.connect(self.set_spatial)

        vlayout.addLayout(flayout)

        self.but = QPushButton("GO", self)
        self.but.setToolTip("Run Rec2CDF")
        self.but.setStyleSheet("color: green")
        self.but.clicked.connect(self.go)
        vlayout.addWidget(self.but)

        hlayout.addLayout(vlayout, stretch=0)
        hlayout.addWidget(smap.browser, stretch=1)

        widget = QWidget()
        widget.setLayout(hlayout)
        splitter.addWidget(widget)

        self.__create_menus()

        # status 'bar' at the bottom
        self.status = TextEditSized(self)
        splitter.addWidget(self.status)

        # I was using appdirs, but doesn't work with python 3.11 and
        # pyinstaller.  keeps trying to load python38.dll
        # adirs = appdirs.AppDirs('Rec2CDF', 'NIWA')
        # self.cdir = cdir = pathlib.Path(adirs.user_data_dir)
        udd = ".local/share" if os.name == "posix" else "AppData/Local"
        self.cdir = cdir = pathlib.Path.home() / udd / "NIWA/Rec2CDF"
        os.makedirs(cdir, mode=0o755, exist_ok=True)
        self.cfile = cdir / "config.ini"
        self.__load_config()

        # before going further, check we can resolve the db server, if not,
        # probably not on NIWA network, and nothing will work
        try:
            hname = self.cp["DEFAULT"].get("dbhost")
            socket.gethostbyname(hname)
        except Exception as exp:
            QMessageBox.critical(
                None,
                "Error",
                f"Can't resolve {hname}, probaby not on NIWA network.  "
                f"Full error was {exp}",
            )
            sys.exit(3)

        if db := self.db_connect("geometries"):
            smap.set_dbcon(db)

        self.setCentralWidget(splitter)

        # get the latest version, and store my version in self.version
        self.version = "unknown"
        self.possibly_update()

    def ridstr_edited(self):
        ridstr = self.ridstr.text()
        try:
            rids = list(map(int, ridstr.strip().split(","))) if ridstr else []
        except Exception as exp:
            QMessageBox.critical(
                self,
                "Error",
                f"Reach IDs must be a comma seperated string.  Full error was {exp}",
            )
            return
        # don't make from scratch, since might have rid/geom already in self.rids
        newrids = {}
        for r in rids:
            if r in self.rids:
                newrids[r] = self.rids[r]
            else:
                g = self.smap.info_for(r)
                if g:
                    newrids[r] = g
        self.rids = newrids
        self.ridstr.setText(",".join(map(str, self.rids.keys())))

        # tell the smap what to display now
        self.smap.display_rids(list(self.rids.values()))

    def rids_toggle(self, rid: int, geom: str):
        if rid in self.rids:
            del self.rids[rid]
        else:
            self.rids[rid] = geom
        self.ridstr.setText(",".join(map(str, self.rids.keys())))

        # tell the smap what to display now
        self.smap.display_rids(list(self.rids.values()))

    def rids_add(self, ridgeom: list):
        """Add reaches to rids

        Parameters
        ----------
        ridgeom: list
            [(rid0, geom0), (rid1, geom1), ...]

        """
        # since self.rids is a dict, it doesn't hurt to add again if it is there
        for rid, geom in ridgeom:
            self.rids[rid] = geom
        self.ridstr.setText(",".join(map(str, self.rids.keys())))

        # tell the smap what to display now
        self.smap.display_rids(list(self.rids.values()))

    def rids_clear(self):
        self.rids = {}
        self.ridstr.setText("")
        self.smap.display_rids(list(self.rids.values()))
        
    def truncatestr_edited(self):
        truncatestr = self.truncatestr.text()
        try:
            truncates = list(map(int, truncatestr.strip().split(","))) if truncatestr else []
        except Exception as exp:
            QMessageBox.critical(
                self,
                "Error",
                f"Truncate IDs must be a comma seperated string.  Full error was {exp}",
            )
            return
        # don't make from scratch, since might have truncate/geom already in self.truncates
        newtruncates = {}
        for r in truncates:
            if r in self.truncates:
                newtruncates[r] = self.truncates[r]
            else:
                g = self.smap.info_for(r)
                if g:
                    newtruncates[r] = g
        self.truncates = newtruncates
        self.truncatestr.setText(",".join(map(str, self.truncates.keys())))

        # tell the smap what to display now
        self.smap.display_truncates(list(self.truncates.values()))


    def truncates_toggle(self, rid: int, geom: str):
        if rid in self.truncates:
            del self.truncates[rid]
        else:
            self.truncates[rid] = geom

        self.truncatestr.setText(",".join(map(str, self.truncates.keys())))
        self.smap.display_truncates(list(self.truncates.values()))

    def truncates_add(self, ridgeom: list):
        """Add reaches to truncates

        Parameters
        ----------
        ridgeom: list
            [(rid0, geom0), (rid1, geom1), ...]

        """
        # since self.truncates is a dict, it doesn't hurt to add again if it is there
        for rid, geom in ridgeom:
            self.truncates[rid] = geom
        self.truncatestr.setText(",".join(map(str, self.truncates.keys())))

        # tell the smap what to display now
        self.smap.display_truncates(list(self.truncates.values()))

    def truncates_clear(self):
        self.truncates = {}
        self.truncatestr.setText("")
        self.smap.display_truncates(list(self.truncates.values()))

    def __create_menus(self):
        bar = self.menuBar()
        self.setMenuBar(bar)

        menu = QMenu("&File", self)
        bar.addMenu(menu)
        action = QAction("&Database", self)
        action.triggered.connect(self.db_prefs)
        menu.addAction(action)
        action = QAction("&Quit", self)
        action.triggered.connect(self.close)
        menu.addAction(action)

        menu = QMenu("&Tools", self)
        bar.addMenu(menu)
        action = QAction("&Trace", self)
        action.triggered.connect(self.trace)
        menu.addAction(action)
        action = QAction("&Save trace", self)
        action.triggered.connect(self.save_trace)
        menu.addAction(action)
        action = QAction("&Clear trace cache", self)
        action.triggered.connect(self.smap.clear_trace_cache)
        menu.addAction(action)

        menu = QMenu("&Help", self)
        bar.addMenu(menu)
        action = QAction("&About", self)
        action.triggered.connect(lambda: self.msg("About", "version.txt"))
        menu.addAction(action)
        action = QAction("&Help", self)
        action.triggered.connect(lambda: self.msg("Help", "help.html"))
        menu.addAction(action)

    def __load_config(self):
        if not self.cfile.exists():
            cp = configparser.ConfigParser()
            cp["DEFAULT"] = {
                "dbhost": "wellhydrodb.niwa.local",
                "dbuser": "hydrology_user",
                "out_dir": pathlib.Path.home() / "Downloads",
            }
            with open(self.cfile, "w") as cfh:
                cp.write(cfh)

        self.cp = configparser.ConfigParser()
        self.cp.read(self.cfile)

    def save_config(self):
        with open(self.cfile, "w") as cfh:
            self.cp.write(cfh)

    def get_installable_versions(self):
        """Return a sorted list of [{'version': version, 'name': name, 'url': url}]"""

        url = "https://api.github.com/repos/niwa/rec2cdf/releases"
        headers = {"Accept": "application/vnd.github+json"}

        try:
            r = requests.get(url, headers=headers)
            r.raise_for_status()
            releases = []
            for release in r.json():
                releases.append(
                    {
                        "version": release["tag_name"],
                        "name": release["assets"][0]["name"],
                        "url": release["assets"][0]["browser_download_url"],
                    }
                )
        except Exception as exp:
            return []

        return sorted(releases, key=lambda i: version.Version(i["version"]), reverse=True)

    def possibly_update(self):
        def __get_ver(fn):
            ver = None
            with open(fn, "r") as fh:
                if ma := re.match(r"Version: (.*)", fh.read()):
                    ver = ma.group(1)
            return ver

        def __download_version(vnu: dict):
            """Download installer and return its path.

            Parameters
            ----------
            vnu: dict
                {'version', 'name', 'url'}

            Returns
            -------
            pathlib.Path
                Path to downloaded installer
            """

            ddir = pathlib.Path(platformdirs.user_downloads_dir())
            installer = ddir / vnu["name"]

            with requests.get(vnu["url"], stream=True) as r:
                r.raise_for_status()

                with open(installer, "wb") as f:
                    for chunk in r.iter_content(chunk_size=8192):
                        f.write(chunk)

            return installer

        # versions from github
        ivers = self.get_installable_versions()
        print(ivers)
        if not ivers:
            return

        # my version
        fname = "version.txt"
        if getattr(sys, "frozen", False):
            fname = pathlib.Path(sys._MEIPASS) / fname
        else:
            me = pathlib.Path(sys.argv[0]).resolve()
            fname = me.parent / fname
        if not (my_ver := __get_ver(fname)):
            return

        # store my version
        self.version = my_ver

        if version.parse(ivers[0]['version']) <= version.parse(my_ver):
            return

        res = QMessageBox.question(
            None,
            "Update",
            "There is a newer version available, shall I install it?",
            QMessageBox.Yes | QMessageBox.No,
            QMessageBox.Yes,
        )
        if res != QMessageBox.Yes:
            return

        # Start download
        try:
            installer = download_version(ivers[0])
        except Exception as e:
            print(f"Download failed: {e}")
            return

        atexit.register(os.execl, installer, installer)
        sys.exit(0)

    def set_spatial(self):
        fname, check = QFileDialog.getSaveFileName(
            self,
            "Spatial file",
            self.cp["DEFAULT"]["out_dir"],
            "NetCDF File (*.nc)",
        )
        if not check:
            return

        # make sure extension is .nc
        if pathlib.Path(fname).suffix != ".nc":
            fname += ".nc"

        # so we use the same directory next time
        self.cp["DEFAULT"]["out_dir"] = str(pathlib.Path(fname).parent)
        self.save_config()

        self.spatial.setText(fname)

    def db_connect(self, db):
        """Connect to database returning opaque reconnectable database object"""
        cp = self.cp["DEFAULT"]
        host = cp.get("dbhost")
        user = cp.get("dbuser")
        if user:
            pw = keyring.get_password("rec2cdf", user)

        if not (host and user and pw):
            QMessageBox.critical(
                self,
                "Error",
                "Cannot connect to database\n\n"
                "Go to File->Database to set up your database connection",
            )
            return

        try:
            # con = psycopg2.connect(
            #    host=host, user=user, password=pw, database=db, keepalives_idle=10
            # )
            con = DB(host, user, pw, db)
        except Exception as exp:
            QMessageBox.critical(
                self,
                "Error",
                f"Cannot connect to database {db}, error was\n{exp}\n\n"
                "Go to File->Database to set up your database connection",
            )
            return

        return con

    def msg(self, title, fname):
        class ScrollableDialog(QDialog):
            def __init__(self, title, txt, parent=None, html=False):
                super().__init__(parent)
                self.setWindowTitle(title)
                btns = QDialogButtonBox(QDialogButtonBox.Ok)
                btns.accepted.connect(self.accept)
                layout = QVBoxLayout()
                te = QTextEdit()
                if html:
                    te.setHtml(txt)
                else:
                    te.setText(txt)
                te.setMinimumWidth(600)
                te.setMinimumHeight(400)
                te.setReadOnly(True)
                layout.addWidget(te)
                layout.addWidget(btns)
                self.setLayout(layout)

        if getattr(sys, "frozen", False):
            fname = pathlib.Path(sys._MEIPASS) / fname
        else:
            me = pathlib.Path(sys.argv[0]).resolve()
            fname = me.parent / fname

        with open(fname) as fh:
            txt = fh.read()
            # if txt is short a messagebox will do
            if txt.count("\n") < 5:
                QMessageBox.information(self, "About", txt)
            else:
                dl = ScrollableDialog(
                    title, txt, parent=self, html=pathlib.Path(fname).suffix == ".html"
                )
                dl.exec()

    def db_prefs(self):
        class DBDialog(QDialog):
            def __init__(self, parent):
                super().__init__(parent)
                self.parent = parent
                self.setWindowTitle("Database")
                btns = QDialogButtonBox(QDialogButtonBox.Cancel | QDialogButtonBox.Ok)
                btns.accepted.connect(self.accept)
                btns.rejected.connect(self.reject)
                layout = QFormLayout()

                cp = parent.cp["DEFAULT"]

                self.host = host = QLineEdit()
                if val := cp.get("dbhost"):
                    host.setText(val)

                self.user = user = QLineEdit()
                if val := cp.get("dbuser"):
                    user.setText(val)

                self.pw = pw = QLineEdit()
                pw.setEchoMode(QLineEdit.Password)
                if user.text():
                    if val := keyring.get_password("rec2cdf", user.text()):
                        pw.setText(val)

                layout.addRow("Host:", host)
                layout.addRow("User:", user)
                layout.addRow("Password:", pw)
                layout.addWidget(btns)
                self.setLayout(layout)

            def accept(self):
                """Test and possibly save."""
                if not (self.host.text() and self.user.text() and self.pw.text()):
                    QMessageBox.critical(
                        self, "Error", "Specify host, user, and password"
                    )
                    return False

                try:
                    psycopg2.connect(
                        host=self.host.text(),
                        user=self.user.text(),
                        password=self.pw.text(),
                        database="template1",
                    )
                except Exception as exp:
                    QMessageBox.critical(
                        self, "Error", f"Could not connect to database:\n{exp}"
                    )
                    return False

                self.parent.cp["DEFAULT"]["dbhost"] = self.host.text()
                self.parent.cp["DEFAULT"]["dbuser"] = self.user.text()
                self.parent.save_config()
                keyring.set_password("rec2cdf", self.user.text(), self.pw.text())

                return super().accept()

        dl = DBDialog(self)
        if dl.exec():
            # connection to template1 worked, if connection to geometries work,
            # tell slippery map about it
            if db := self.db_connect("geometries"):
                self.smap.set_dbcon(db)

    def save_trace(self):
        """If the user has done an upstream trace, save it."""
        if self.smap.tracedf == []:
            QMessageBox.critical(self, "Error", "Must perform trace first")
            return False

        fname, check = QFileDialog.getSaveFileName(
            self,
            "Trace file",
            self.cp["DEFAULT"]["out_dir"],
            "GeoPackage File (*.gpkg)",
        )
        if not check:
            return

        # make sure extension is .gpkg
        if pathlib.Path(fname).suffix != ".gpkg":
            fname += ".gpkg"

        # so we use the same directory next time
        self.cp["DEFAULT"]["out_dir"] = str(pathlib.Path(fname).parent)
        self.save_config()

        # attempt to delete output file, otherwise can get a lot of different
        # layers in there
        try:
            os.unlink(fname)
        except OSError:
            pass

        t = pd.concat(self.smap.tracedf, ignore_index=True)
        t.drop(columns="watershed").set_geometry("geom").to_crs(2193).to_file(
            fname, layer="line", driver="GPKG"
        )
        t[["nzreach", "watershed"]].set_geometry("watershed").to_crs(2193).to_file(
            fname, layer="wshed", driver="GPKG"
        )
        t[["nzreach", "watershed"]].set_geometry("watershed").to_crs(
            2193
        ).dissolve().to_file(fname, layer="catchment", driver="GPKG")

        QMessageBox.information(self, "Saved", f"Written to {fname}")
        

    def trace(self):
        rids = self.rids
        if not rids:
            QMessageBox.critical(self, "Error", "Must set reach ID")
            return False

        try:
            [int(r) for r in rids]
        except Exception:
            QMessageBox.critical(
                self, "Error", "Reach IDs must be comma seperated integers"
            )
            return False

        for r in rids:
            if not (1e6 <= r <= 16e6):
                QMessageBox.critical(
                    self, "Error", "Reach ID must be between 1 and 16 million"
                )
                return False

        self.smap.trace(list(rids.keys()), list(self.truncates.keys()))

    def go(self):
        rids = self.rids
        if not rids:
            QMessageBox.critical(self, "Error", "Must set reach ID")
            return False

        try:
            [int(r) for r in rids]
        except Exception:
            QMessageBox.critical(
                self, "Error", "Reach IDs must be comma seperated integers"
            )
            return False

        for r in rids:
            if not (1e6 <= r <= 16e6):
                QMessageBox.critical(
                    self, "Error", "Reach ID must be between 1 and 16 million"
                )
                return False

        # if dn3, all rids must be in same region
        if self.dn.currentText() == "3":
            reg = int(list(rids.keys())[0] // 1e6)
            if not all(int(rid // 1e6) == reg for rid in rids):
                QMessageBox.critical(
                    self, "Error", f"For DN3 all rids must be in same region, you have rids {list(rids.keys())}"
                )
                return False

        spatial = self.spatial.text()
        if not spatial:
            QMessageBox.critical(self, "Error", "Must set output spatial filename")
            return False

        # make sure we can connect
        if not self.db_connect("template1"):
            QMessageBox.critical(
                self,
                "Error",
                "Cannot connect to database\n\n"
                "Go to File->Database to set up your database connection",
            )
            return False

        if self.dn.currentText() == "1":
            dbname = "rec1"
        elif self.dn.currentText() == "2":
            dbname = "dn25"
        else:
            dbname = rid_to_db(list(rids.keys())[0])

        # clean up the log file if already exists so the watcher doesn't pick
        # up an old file
        try:
            pathlib.Path(spatial).with_suffix(".log").unlink(missing_ok=True)
            pathlib.Path(spatial).unlink(missing_ok=True)
        except Exception:
            # I had a critical error here before, but it is annoying since
            # sometimes the watcher doesn't close the log file, so we can't
            # delete it, and hence raise Exception.  But I don't think it
            # matters if the watcher picks up old file.
            pass
            # QMessageBox.critical(
            #    self, 'Error',
            #    f'Could not clean output files:\n\nExact error is {exp}'
            # )
            # return False

        # watch the log file, outputting each line in the statusbar
        self.watcher = Watcher(f"{pathlib.Path(spatial).with_suffix('.log')}")

        # this runs rec2cdf
        self.worker_thd = QThread()
        self.worker = Worker(
            dbname,
            self.cp["DEFAULT"]["dbhost"],
            self.cp["DEFAULT"]["dbuser"],
            keyring.get_password("rec2cdf", self.cp["DEFAULT"]["dbuser"]),
            f"{pathlib.Path(spatial).with_suffix('.log')}",
            spatial,
            list(rids.keys()),
            self.bsites.isChecked(),
            self.blakes.isChecked(),
            self.regional.isChecked(),
            int(self.order.currentText()),
            self.version,
            list(self.truncates.keys()),
        )
        self.worker.moveToThread(self.worker_thd)
        self.worker_thd.started.connect(self.job_started)
        self.worker_thd.started.connect(self.worker.run)
        self.worker.finished.connect(self.worker_thd.quit)
        self.worker.finished.connect(self.worker.deleteLater)
        self.worker_thd.finished.connect(self.worker_thd.deleteLater)
        self.worker_thd.finished.connect(self.job_finished)
        self.worker_thd.finished.connect(self.watcher.finish)
        self.worker_thd.start()

        # thread to run the watcher
        self.watch_thd = QThread()
        self.watcher.display.connect(self.status_display)
        self.watcher.moveToThread(self.watch_thd)
        self.watch_thd.started.connect(self.watcher.run)
        self.watcher.finished.connect(self.watch_thd.quit)
        self.watcher.finished.connect(self.watcher.deleteLater)
        self.watch_thd.finished.connect(self.watch_thd.deleteLater)
        self.watch_thd.start()

    def job_started(self):
        self.but.setEnabled(False)
        self.but.setText("Working...")
        self.but.setStyleSheet("color: grey")

    def job_finished(self):
        self.but.setEnabled(True)
        self.but.setText("GO")
        self.but.setStyleSheet("color: green")
        self.status_display("JOB DONE")

    @pyqtSlot(str)
    def status_display(self, msg):
        # self.status.appendPlainText(bytes(msg).decode("utf8"))
        self.status.appendPlainText(msg)
        endl = self.status.verticalScrollBar().maximum()
        endl = max(0, endl - 1)
        self.status.verticalScrollBar().setValue(endl)


if __name__ == "__main__":
    app = QApplication(sys.argv)
    win = Window()
    win.show()
    sys.exit(app.exec_())
