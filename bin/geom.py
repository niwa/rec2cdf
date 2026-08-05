import logging
import psycopg2.extras
import numpy as np
from var_collection import VarCollection


class Geom(VarCollection):
    """
    A lot of Geom variables

    Variables
    --------

    This class defines a lot of variables, the definitions of such can be
    found in attr_info.jinja, but a summary is provided here.  The
    dimension is in parenthesis

    basarea_noagg(nrch_noagg)
        catchment area for each individual reach

    basarea(nrch)
        sum of catchment areas of reaches in aggregate

    baselev_noagg(nrch_noagg)
        average elevation for each individual reach

    baselev(nrch)
        average, weighted by catchment area, of baselev_noagg

    basmaxelev(nrch)
        max over reaches in aggregate of basmaxelev

    basminelev(nrch)
        min over reaches in aggregate of basminelev

    basstdelev(nrch)
        max over reaches in aggregate of basstdelev

    cen_lat(nrch)
    cen_lon(nrch)
    cen_nzmge(nrch)
    cen_nzmgn(nrch)
        average, weighted by catchment area, of individual reach cen_lat etc

    end_lat(nrch)
    end_lon(nrch)
    end_nzmge(nrch)
    end_nzmgn(nrch)
        bottom most reach in aggregate end_lat etc

    nonaggrch_area(nrch, maxe)
    nonaggrch_elev(nrch, maxe)
        A row per aggregate containing the areas (or elevation) of the non
        aggregate reaches, except for the first element which is the area/elev
        for the aggregate.  Ie nonaggrch_area[i, 0] = basarea[i].  The order
        within a row matches the nonaggrch_nrch variable.

    nonaggrch_frq(nrch, maxe)
        All nans

    rchlength(nrch)
        Sum of the lengths of the significant reaches in aggregate, if none,
        then the bottom most reach

    rchman_n(nrch)
        average, weighted by reach length of significant reaches, of rchman_n

    rchmaxelev(nrch)
    rchminelev(nrch)
        max or min over significant reaches of rchmaxelev or rchminelev

    rchslope(nrch)
        average, weighted by lengths of significatn reaches, of slope, where
        slope is max of 0.005 and (upelev-downelev)/length.

    rchwidth(nrch)
        width of bottom most reach in aggregate

    start_lat(nrch)
    start_lon(nrch)
    start_nzmge(nrch)
    start_nzmgn(nrch)
        Location of the
        downstream point of the upstream aggregate, or for a leaf the top end
        of the bottom most reach in the aggregate.

    streamorder(nrch)
        Order of bottom most reach in aggregate

    uparea(nrch)
        accarea of bottom most reach in aggregate

    """

    def dfn_vars(self):
        # need info for all reaches
        allreaches = ",".join(map(str, self.top.rids))

        ######################################################################
        # info for reaches
        q = f"""
            SELECT
                rchid,
                catcharea as basarea_noagg, 
                COALESCE(aveelev,-9999) as baselev_noagg,
                COALESCE(minelev,-9999) as basminelev, 
                COALESCE(maxelev,-9999) as basmaxelev,
                COALESCE(stdelev,-9999) as basstdelev,
                COALESCE(cen_lat, -9999) as cen_lat,
                COALESCE(cen_lon, -9999) as cen_lon, 
                COALESCE(cen_x, -9999) as cen_nzmge,
                COALESCE(cen_y, -9999) as cen_nzmgn, 
                COALESCE(end_lat, -9999) as end_lat,
                COALESCE(end_lon, -9999) as end_lon, 
                COALESCE(end_x, -9999) as end_nzmge,
                COALESCE(end_y, -9999) as end_nzmgn, 
                length as rchlength,
                CAST({self.attrs['default_mannings']} AS float) as rchman_n,
                upelev AS rchmaxelev, 
                downelev AS rchminelev,
                GREATEST(
                    ceil((sign(upelev-downelev)+1)/2)*((upelev-downelev)/length),
                    0.0005
                ) AS rchslope, 
                (
                    {self.attrs['stream_width_a']} *
                    POW(accarea, {self.attrs['stream_width_b']})
                ) AS rchwidth, 
                COALESCE(start_lat, -9999) as start_lat,
                COALESCE(start_lon, -9999) as start_lon, 
                COALESCE(start_x, -9999) as start_nzmge,
                COALESCE(start_y, -9999) as start_nzmgn, 
                streamorder, 
                accarea as uparea
            FROM reach 
            WHERE 
                rchid >= {min(self.top.rids)} AND
                rchid <= {max(self.top.rids)} AND
                rchid IN ({allreaches}) AND
                catcharea > 0 AND accarea > 0 
            ORDER BY reach.accarea DESC
        """
        logging.debug(f"Geom values using query {q}")
        cur = self.con.cursor(cursor_factory=psycopg2.extras.DictCursor)
        cur.execute(q)
        logging.info(f"Geom values for {cur.rowcount} reaches")

        # map rin to dict of info
        r2info = {
            self.top.rid_to_rin[row["rchid"]]: {v: row[v] for v in row.keys()}
            for row in cur.fetchall()
        }
        # if the network is truncated, uparea will be wrong
        if self.top.truncates:
            # wipe out all upareas
            for info in r2info.values():
                info["uparea"] = 0

            # recursive method to recalculate
            def uparea(rin):
                me = r2info[rin]
                if me["uparea"] == 0:
                    me["uparea"] = me["basarea_noagg"] + sum(
                        uparea(u) for u in self.top.rin_to_ups[rin]
                    )
                return me["uparea"]

            # fill in newuparea starting from top of catchment to avoid too
            # much recursion
            for rin in sorted(r2info.keys(), reverse=True):
                uparea(rin)

        # just copy in for non-aggregated values
        for v in ("basarea_noagg", "baselev_noagg"):
            self.v2val[v][:] = [r2info[rin][v] for rin in range(len(self.top.rids))]

        # aggregated values need min, max, summing or averaging
        for ain, rins in enumerate(self.top.ain_to_rins):
            # areas of all reaches in this aggregate
            areas = [r2info[rin]["basarea_noagg"] for rin in rins]

            # rins of significant reaches
            sigs = [rin for rin in rins if self.top.rin_to_sig[rin]]

            # significant lengths
            slens = [r2info[rin]["rchlength"] for rin in sigs]

            self.v2val["basarea"][ain] = sum(areas)

            self.v2val["baselev"][ain] = np.average(
                [r2info[rin]["baselev_noagg"] for rin in rins], weights=areas
            )
            for v in ("cen_lat", "cen_lon", "cen_nzmge", "cen_nzmgn"):
                self.v2val[v][ain] = np.average(
                    [r2info[rin][v] for rin in rins], weights=areas
                )

            # max over reaches
            for v in ("basmaxelev", "basstdelev"):
                self.v2val[v][ain] = max(r2info[rin][v] for rin in rins)

            # min over reaches
            for v in ("basminelev",):
                self.v2val[v][ain] = min(r2info[rin][v] for rin in rins)

            # max of significant reaches
            self.v2val["rchmaxelev"][ain] = max(r2info[i]["rchmaxelev"] for i in sigs)

            # rchminlev is min over sig reaches
            self.v2val["rchminelev"][ain] = min(r2info[i]["rchminelev"] for i in sigs)

            # length is sum of significant (or first) lengths.
            self.v2val["rchlength"][ain] = sum(r2info[rin]["rchlength"] for rin in sigs)

            # average, weighted by significant lengths
            for v in ("rchman_n", "rchslope"):
                self.v2val[v][ain] = np.average(
                    [r2info[rin][v] for rin in sigs], weights=slens
                )

            # just the first reach in the aggregate
            for v in (
                "rchwidth",
                "streamorder",
                "uparea",
                "end_lat",
                "end_lon",
                "end_nzmge",
                "end_nzmgn",
            ):
                self.v2val[v][ain] = r2info[rins[0]][v]

            # the 2d arrays for nonagg vals. overwrite first with the aggregate val
            for v in ("area", "elev"):
                for i, rin in enumerate(rins):
                    self.v2val[f"nonaggrch_{v}"][ain][i] = r2info[rin][f"bas{v}_noagg"]
                self.v2val[f"nonaggrch_{v}"][ain][0] = self.v2val[f"bas{v}"][ain]

        # start locations are set using the upstream end location, so do these
        # after end locations sorted
        for ain, rins in enumerate(self.top.ain_to_rins):
            if ups := self.top.ain_to_ups[ain]:
                self.v2val["start_lat"][ain] = self.v2val["end_lat"][ups[0]]
                self.v2val["start_lon"][ain] = self.v2val["end_lon"][ups[0]]
                self.v2val["start_nzmge"][ain] = self.v2val["end_nzmge"][ups[0]]
                self.v2val["start_nzmgn"][ain] = self.v2val["end_nzmgn"][ups[0]]
            else:
                # no upstream aggregate, we are a leaf, use the start of
                # bottom most reach.
                rin = rins[0]
                self.v2val["start_lat"][ain] = r2info[rin]["start_lat"]
                self.v2val["start_lon"][ain] = r2info[rin]["start_lon"]
                self.v2val["start_nzmge"][ain] = r2info[rin]["start_nzmge"]
                self.v2val["start_nzmgn"][ain] = r2info[rin]["start_nzmgn"]

        # fix rchwidth comment to be dynamic
        self.v2info["rchwidth"]["attributes"]["comment"] = (
            f"Calculated as {self.attrs['stream_width_a']} * "
            f"area ^ {self.attrs['stream_width_b']}"
        )

        def get_llength(rin):
            down = self.top.rin_to_ds[rin]
            if self.top.rin_to_sig[rin]:
                return 0
            else:
                return r2info[rin]["rchlength"] + get_llength(down)

        self.top.llength_all = [get_llength(rin) for rin in range(len(self.top.rids))]
        self.top.basarea_noagg = self.v2val["basarea_noagg"]
        self.top.basarea = self.v2val["basarea"]
