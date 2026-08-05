import logging
import psycopg2.extras
import numpy as np
from var_collection import VarCollection
from utils import PositiveFreqDistribution as PFD


class Wetness(VarCollection):
    """Wetness variables, atanval, atanfrq, lambda and numatan"""

    def dfn_vars(self):
        maxval = 30
        binthres = 1
        freqthres = 0.05

        # need info for all reaches
        allreaches = ",".join(map(str, self.top.rids))
        q = f"""
            SELECT reach.rchid, value, frequency, reach.catcharea
            FROM reach LEFT OUTER JOIN atbfreq ON atbfreq.rchid=reach.rchid
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
        logging.debug(f"Wetness values query {q}")
        cur = self.con.cursor(cursor_factory=psycopg2.extras.DictCursor)
        cur.execute(q)
        logging.info(f"Total number of wetness values is {cur.rowcount}")

        # will map rin to values, frequency*area dict
        r2vf = {}
        for row in cur.fetchall():
            r2vf.setdefault(row["rchid"], {}).setdefault("val", []).append(row["value"])
            r2vf.setdefault(row["rchid"], {}).setdefault("freq", []).append(
                row["frequency"] * row["catcharea"]
            )
        r2fd = {
            self.top.rid_to_rin[r]: PFD(vf["val"], vf["freq"]) for r, vf in r2vf.items()
        }
        cur.close()

        # combine all the PFDs within an aggregate.  doesn't hurt to do this if
        # order>1 since rin==ain and only one reach per agg
        a2fd = {}
        for rin, fd in r2fd.items():
            ain = self.top.rin_to_ain[rin]
            a2fd.setdefault(ain, []).append(fd)
        r2fd = {ain: PFD.combine(fds) for ain, fds in a2fd.items()}

        # maps ain/rin to val * freq
        r2lambda = {}
        for ind, fd in r2fd.items():
            fd.freqs = list(fd.freqs / self.top.basarea[ind])
            fd.set_max_bin(maxval)

            # old rec2cdf only did this for order > 1, makes more sense for all
            fd.rm_small_bins(binthres, freqthres)

            fd.relative()

            # weighted sum of val/freq
            r2lambda[ind] = np.dot([b[1] for b in fd.bins], fd.freqs)
            fd.cumulative()
            fd.freqs[-1] = 1  # it should be, but force incase not

        # finally we can fill in the variables.
        for ind, fd in r2fd.items():
            n = len(fd.bins) + 1
            self.v2val["lambda"][ind] = r2lambda[ind]
            self.v2val["numatan"][ind] = n
            self.v2val["atanval"][ind, :n] = [0] + [b[1] for b in fd.bins]
            self.v2val["atanfrq"][ind, :n] = [0] + [i for i in fd.freqs]
