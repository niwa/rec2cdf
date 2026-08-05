import logging
import psycopg2.extras
from var_collection import VarCollection


class Lake(VarCollection):
    """A lot of lake variables"""

    def preamble(self):
        self.allreaches = ",".join(map(str, self.top.rids))

        ######################################################################
        # info for reaches that intersect lakes
        q = f"""
            SELECT rch_lake_area.rchid, rch_lake_area.lakeid, rch_lake_area.area, 
                    rch_lake_area.length
            FROM lake, rch_lake_area 
            WHERE
                lake.lakeid = rch_lake_area.lakeid AND 
                lake.ds_rchid != rch_lake_area.rchid AND 
                rch_lake_area.rchid >= {min(self.top.rids)} AND
                rch_lake_area.rchid <= {max(self.top.rids)} AND
                rch_lake_area.rchid IN ({self.allreaches})
            ORDER BY rch_lake_area.area DESC
        """
        logging.debug(f"Lakes values query {q}")
        cur = self.con.cursor(cursor_factory=psycopg2.extras.DictCursor)
        cur.execute(q)
        logging.info(f"Lakes values {cur.rowcount} reaches")

        # maps rin to {'lid': lake id, 'area': area, 'length': length}
        r2lake = {
            self.top.rid_to_rin[row["rchid"]]: {
                "lid": row["lakeid"],
                "area": row["area"],
                "length": row["length"],
            }
            for row in cur.fetchall()
        }
        self.r2lake = r2lake

        # a list of lake ids, and reverse
        self.lids = lids = list(set(info["lid"] for info in r2lake.values()))
        self.lid_to_lin = {lid: i for i, lid in enumerate(lids)}

        # setup_vars now that we know how many lakes there are
        self.nlakes = nlakes = len(lids)
        self.setup_dim("nlake", nlakes)
        self.attrs.update({"nlake": nlakes})

    def dfn_vars(self):
        # if none, we are done
        if self.nlakes == 0:
            return

        # maps ain to lake info but summing areas, and adding (non positive) lengths
        a2lake = {}
        for rin, lake in self.r2lake.items():
            ain = self.top.rin_to_ain[rin]
            if ain not in a2lake:
                a2lake[ain] = {"lid": lake["lid"], "area": 0, "length": 0}
            a2lake[ain]["area"] += lake["area"]
            if a2lake[ain]["length"] == 0 or self.top.llength_all[rin] <= 0:
                a2lake[ain]["length"] += lake["length"]

        self.v2val["lakeid"][:] = self.lids
        self.v2val["lakeindex"][:] = list(range(self.nlakes))
        for ain, lake in a2lake.items():
            self.v2val["rch_nlake"][ain] = self.lid_to_lin[lake["lid"]]
            self.v2val["rch_lakeid"][ain] = lake["lid"]
            self.v2val["rch_lake_area"][ain] = lake["area"]
            self.v2val["rch_lake_length"][ain] = lake["length"]

        ######################################################################
        # area and length for each lake
        q = f"""
            SELECT rch_lake_area.lakeid, rch_lake_area.area, rch_lake_area.length
            FROM lake, rch_lake_area 
            WHERE lake.lakeid = rch_lake_area.lakeid AND 
                lake.ds_rchid = rch_lake_area.rchid AND 
                rch_lake_area.rchid >= {min(self.top.rids)} AND
                rch_lake_area.rchid <= {max(self.top.rids)} AND
                rch_lake_area.rchid IN ({self.allreaches})
            ORDER BY rch_lake_area.area DESC
        """
        logging.debug(f"Lake area/length query {q}")
        cur = self.con.cursor(cursor_factory=psycopg2.extras.DictCursor)
        cur.execute(q)
        logging.info(f"Lake area/length for {cur.rowcount} lakes")

        # maps lid to {'area': area, 'length': length}.
        # NB: we don't necessarily get info for all lakes because of the
        # lake.ds_rchid = rch_lake_area.rchid instead of != above.
        lid2lake = {
            row["lakeid"]: {"area": row["area"], "length": row["length"]}
            for row in cur.fetchall()
        }

        # default zero for outlets not associated with lake
        self.v2val["lk_ds_area"][:] = 0
        self.v2val["lk_ds_length"][:] = 0
        for lid, lake in lid2lake.items():
            if lid in self.lid_to_lin:
                lin = self.lid_to_lin[lid]
                self.v2val["lk_ds_area"][lin] = lake["area"]
                self.v2val["lk_ds_length"][lin] = lake["length"]

        ######################################################################
        # downstream lake or reach
        q = f"""
            SELECT lakeid, ds_lakeid, ds_rchid
            FROM lake
            WHERE lakeid IN ({','.join(map(str, self.lids))})
        """
        logging.debug(f"Lake downstream lake/reach query {q}")
        cur = self.con.cursor(cursor_factory=psycopg2.extras.DictCursor)
        cur.execute(q)
        logging.info(f"Lake downstream lake/reach for {cur.rowcount} lakes")

        # maps ain to a list of upstream lin
        ain_to_uplins = {}

        # maps lakeid to info
        lid2lake = {
            row["lakeid"]: {
                "lk_ds_lakeid": row["ds_lakeid"],
                "lk_ds_rchid": row["ds_rchid"],
            }
            for row in cur.fetchall()
        }

        # print(lid2lake)

        for lid, info in lid2lake.items():
            lin = self.lid_to_lin[lid]

            # if a lake feeds into a downstream lake in this domain then fill in
            # lk_ds_lakeid and lk_ds_nlake (these are lists from lin to
            # downstream lakeid and lake index).
            ds_lid = info["lk_ds_lakeid"]
            if ds_lid is not None and ds_lid > 0 and ds_lid in self.lids:
                self.v2val["lk_ds_lakeid"][lin] = ds_lid
                self.v2val["lk_ds_nlake"][lin] = self.lid_to_lin[ds_lid]

            # no downstream reach is fine according to old code, not sure if
            # this ever happens.
            rid = info["lk_ds_rchid"]
            if rid is None or rid <= 0:
                continue

            # downstream reach in domain is good
            if rid in self.top.rids:
                # print(f"{rid=}")
                # print(f"{self.top.rid_to_rin=}")
                # print(f"{self.top.rin_to_ain=}")
                ain = self.top.rin_to_ain[self.top.rid_to_rin[rid]]
                aid = self.top.aids[ain]
                # print(f"Checking {rid}, its aid is {aid}")
                self.v2val["lk_ds_rchid"][lin] = aid
                self.v2val["lk_ds_nrch"][lin] = ain
                # add usptream lake to downstream reach
                ain_to_uplins.setdefault(ain, []).append(lin)
            else:
                logging.error(f"Outlet rid {rid} for lake {lid} not in model domain")

        # the number of lakes above each reach
        self.v2val["numuplk"][:] = 0
        for ain, lins in ain_to_uplins.items():
            self.v2val["numuplk"][ain] = len(lins)
            self.v2val["uprch_nlake"][ain][: len(lins)] = lins
            self.v2val["uprch_lakeid"][ain][: len(lins)] = [self.lids[i] for i in lins]
        self.v2info["uprch_lakeid"]["attributes"]["valid_max"] = max(self.lids)
        self.v2info["uprch_nlake"]["attributes"]["valid_max"] = len(self.lids) - 1

        ######################################################################
        # data for each lake
        q = f"""
            SELECT lakeid,
                arearef AS "lk_refarea",
                elevationref AS "lk_refelev",
                depthref AS "lk_refdeph",
                SHAPE_M AS "lk_shape_m",
                HE2AR_C AS "lk_he2ar_c",
                HE2AR_D AS "lk_he2ar_d",
                HGHTSPL AS "lk_hghtspl",
                HGHTECO AS "lk_hghteco",
                HGHTLOW AS "lk_hghtlow",
                DSCHECO AS "lk_dscheco",
                DSCHSPL AS "lk_dschspl",
                RTCPRMA AS "lk_ratecva",
                RTCPRMB AS "lk_ratecvb"
            FROM lake
            WHERE lakeid IN ({','.join(map(str, self.lids))})
        """
        logging.debug(f"Lake data query {q}")
        cur = self.con.cursor(cursor_factory=psycopg2.extras.DictCursor)
        cur.execute(q)
        logging.info(f"Lake data for {cur.rowcount} lakes")

        lvars = [
            "lk_refarea",
            "lk_refelev",
            "lk_refdeph",
            "lk_shape_m",
            "lk_he2ar_c",
            "lk_he2ar_d",
            "lk_hghtspl",
            "lk_hghteco",
            "lk_hghtlow",
            "lk_dscheco",
            "lk_dschspl",
            "lk_ratecva",
            "lk_ratecvb",
        ]
        for row in cur.fetchall():
            lin = self.lid_to_lin[row["lakeid"]]
            for v in lvars:
                if row[v]:
                    self.v2val[v][lin] = row[v]
        ######################################################################
