import logging
import numpy as np
import psycopg2.extras
from var_collection import VarCollection


class Soil_Veg(VarCollection):
    def preamble(self):
        self.ki = self.ki_vars()

    def ki_vars(self):
        """Return True if ki variables in db

        Currently 2022-08-05 only in rec2, but eventually hopefully in all dbs
        """
        try:
            cur = self.con.cursor()
            cur.execute(
                """
                SELECT
                column_name
                FROM information_schema.columns
                WHERE table_name='toppar' and column_name='ki'
            """
            )
            if cur.fetchone():
                cur.close()
                return True
        except Exception:
            pass
        return False

    def ki_select(self):
        """Return the ki selection query if ki present

        Currently 2022-08-05 only in rec2, but eventually hopefully in all dbs
        """
        if self.ki:
            return """,
                CAST(COALESCE(rpawstar, 0.5) AS float)  AS rpawstar,
                CAST(COALESCE(mpor_s, 5) AS float)  AS mpor_s,
                CAST(COALESCE(mpor_d, 5) AS float)  AS mpor_d,
                CAST(COALESCE(prd_mid,0.5) AS float)  AS prd_mid,
                CAST(COALESCE(paw_mid, 140) AS float)  AS paw_mid,
                CAST(COALESCE(alpha_irrig, 1) AS float)  AS alpha_irr,
                CAST(COALESCE(malf_7, 0.5) AS float)  AS malf_7,
                CAST(COALESCE(irrig_area, 1000) AS float) AS irrig_area,
                CAST(COALESCE(ki, 150) AS float) AS ki 
            """
        return ""

    def dfn_vars(self):
        allreaches = ",".join(map(str, self.top.rids))
        q = f"""
            SELECT
                reach.rchid,
                reach.lowerreach, 
                CAST(COALESCE(topmodf, 12.4) AS float) AS topmodf, 
                CAST(
                    CASE WHEN (COALESCE(dth1,0.14) + COALESCE(dth2,0.2)) > 0 
                    THEN (
                        COALESCE(soil_cap,0.082)/(COALESCE(dth1,0.14)+COALESCE(dth2,0.2))
                    )
                    ELSE 0.0
                    END AS float
                ) AS topmodm, 
                CAST(0.1 AS float) AS topmodn, 
                CAST(COALESCE(hydcon0, 0.01) AS float) AS hydcon0, 
                CAST(COALESCE(dth1, 0.14) AS float) AS dtheta1, 
                CAST(COALESCE(dth2, 0.2) AS float)  AS dtheta2, 
                CAST(COALESCE(soil_cap, 0.082) AS float) AS soilcap, 
                CAST(1.0 AS float) AS ch_cexp, 
                CAST(COALESCE(ga_psif, 0.3) AS float) AS ga_psif, 
                CAST(0.1 AS float) AS overvel, 
                CAST(COALESCE(can_cap, 0.0017) AS float) AS canscap, 
                CAST(COALESCE(can_en, 2.0) AS float) AS canenhf, 
                CAST(COALESCE(salbedo, 0.2) AS float) AS salbedo, 
                CAST(0.0065 AS float) AS atmlaps, 
                CAST(5.0 AS float) AS snowddf, 
                CAST(273.15 AS float) AS accmelt, 
                CAST(274.16 AS float) AS th_accm, 
                CAST(273.16 AS float) AS th_melt, 
                CAST(1.0 AS float) AS gucatch, 
                CAST(1.0 AS float) AS cv_snow, 
                CAST(0.0 AS float) AS tncoeff, 
                CAST(0.0 AS float) AS windcal, 
                CAST(5.0 AS float) AS snowamp, 
                CAST(0.0 AS float) AS snowros, 
                CAST(2.5 AS float) AS decmelt, 
                CAST(5.0 AS float) AS albdecy, 
                CAST(0.0 AS float) AS sdevtmp, 
                CAST(0.01 AS float) AS watflow, 
                CAST(0.85 AS float) AS fsnoalb, 
                CAST(0.5 AS float) AS osnoalb, 
                CAST(-3.0 AS float) AS snowz0n, 
                CAST(20.0 AS float) AS snocond, 
                CAST(0.0005 AS float) AS canstor, 
                CAST(0.05 AS float) AS soilh2o, 
                CAST(0.25 AS float) AS zbarh2o
                {self.ki_select()}
            FROM reach, toppar 
            WHERE
                reach.rchid = toppar.rchid and 
                reach.rchid >= {min(self.top.rids)} AND
                reach.rchid <= {max(self.top.rids)} AND
                reach.rchid IN ({allreaches}) AND
                reach.catcharea > 0 AND
                reach.accarea > 0
            ORDER BY reach.accarea DESC
        """
        logging.debug(f"Soil_veg query {q}")
        cur = self.con.cursor(cursor_factory=psycopg2.extras.DictCursor)
        cur.execute(q)
        logging.info(f"Soil_veg values for {cur.rowcount} reaches")

        # map var name to np.array of data for each reach (not aggregate)
        # if not doing ki, don't make room for those
        data = {
            v: np.full(len(self.top.rids), -9999, dtype="float")
            for v, info in self.v2info.items()
            if not info["ki"] or (info["ki"] and self.ki)
        }

        logging.info("Soil_veg reading data")
        for row in cur.fetchall():
            rin = self.top.rid_to_rin[row["rchid"]]
            for name, arr in data.items():
                arr[rin] = row[name]
        cur.close()

        # we can aggregate even if order==1, just doesn't do anything, but at
        # least we get v2val filled up
        logging.info("Soil_veg aggregate data")
        weights = np.array(self.top.basarea_noagg)
        for name, arr in data.items():
            for ain, rins in enumerate(self.top.ain_to_rins):
                self.v2val[name][ain] = np.average(
                    data[name][rins], weights=weights[rins]
                )
