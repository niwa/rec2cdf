import logging
import math
import numpy as np
import psycopg2.extras
from var_collection import VarCollection
from utils import PositiveFreqDistribution as PFD


class Stream_Distance(VarCollection):
    """overval, overfrq and numover variables"""

    def dfn_vars(self):
        maxval = 20000
        binthres = 200
        freqthres = 0.01

        # need info for all reaches
        allreaches = ",".join(map(str, self.top.rids))
        q = f"""
            SELECT reach.rchid, value, frequency, reach.catcharea
            FROM reach LEFT OUTER JOIN distfreq ON distfreq.rchid=reach.rchid
            WHERE
                reach.rchid >= {min(self.top.rids)} AND
                reach.rchid <= {max(self.top.rids)} AND
                reach.rchid IN ({allreaches}) AND
                reach.catcharea > 0 AND
                reach.accarea > 0 AND
                value > 0 AND
                frequency > 0
            ORDER BY reach.accarea DESC, reach.rchid ASC, value ASC, frequency ASC
        """
        logging.debug(f"{self.name} query {q}")
        cur = self.con.cursor(cursor_factory=psycopg2.extras.DictCursor)
        cur.execute(q)
        logging.info(f"Total number of {self.name} values is {cur.rowcount}")

        # will map rin to values, frequency*value dict
        r2vf = {}
        for row in cur.fetchall():
            r2vf.setdefault(row["rchid"], {}).setdefault("val", []).append(row["value"])
            r2vf.setdefault(row["rchid"], {}).setdefault("freq", []).append(
                row["frequency"] * row["catcharea"]
            )
        cur.close()

        # some reaches are missing in database, put in default
        for rid in set(self.top.rids) - set(r2vf.keys()):
            rin = self.top.rid_to_rin[rid]
            r2vf[rid] = {
                "val": [math.sqrt(self.top.basarea_noagg[rin])],
                "freq": [self.top.basarea_noagg[rin]],
            }
        # all values need to have llength_all added
        for rid, vf in r2vf.items():
            rin = self.top.rid_to_rin[rid]
            vf["val"] = list(np.array(vf["val"]) + self.top.llength_all[rin])

        # make into distributions
        r2fd = {
            self.top.rid_to_rin[r]: PFD(vf["val"], vf["freq"]) for r, vf in r2vf.items()
        }

        # combine all the PFDs within an aggregate.  doesn't hurt to do this if
        # order>1 since rin==ain and only one reach per agg
        a2fd = {}
        for rin, fd in r2fd.items():
            ain = self.top.rin_to_ain[rin]
            a2fd.setdefault(ain, []).append(fd)
        r2fd = {ain: PFD.combine(fds) for ain, fds in a2fd.items()}

        for ind, fd in r2fd.items():
            fd.freqs = list(fd.freqs / self.top.basarea[ind])
            fd.set_max_bin(maxval)
            # old code only did for order > 1, makes more sense to do for all
            fd.rm_small_bins(binthres, freqthres)
            fd.relative()
            fd.cumulative()
            fd.freqs[-1] = 1  # it should be, but force incase not

        for ind, fd in r2fd.items():
            n = len(fd.bins) + 1
            self.v2val["numover"][ind] = n
            self.v2val["overval"][ind, :n] = [0] + [b[1] for b in fd.bins]
            self.v2val["overfrq"][ind, :n] = [0] + [i for i in fd.freqs]
