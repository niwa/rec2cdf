import logging
import psycopg2.extras
from var_collection import VarCollection
from utils import PositiveFreqDistribution as PFD


class Elevation(VarCollection):
    """Elevation variables: elevval, elevfrq, and numelev"""

    def dfn_vars(self):
        maxval = 9000

        # need info for all reaches
        allreaches = ",".join(map(str, self.top.rids))
        q = f"""
            SELECT reach.rchid, value, frequency, reach.catcharea
            FROM reach LEFT OUTER JOIN elevfreq ON elevfreq.rchid=reach.rchid
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
        logging.debug(f"Elevation query {q}")
        cur = self.con.cursor(cursor_factory=psycopg2.extras.DictCursor)
        cur.execute(q)
        logging.info(f"Elevation values for {cur.rowcount} reaches")

        # will map rin to values, frequency*value dict
        r2vf = {}
        for row in cur.fetchall():
            rid = row["rchid"]
            val = row["value"]
            if rid not in r2vf:
                r2vf[rid] = {"val": [val - 50], "freq": [0]}
            r2vf[rid]["val"].append(val)
            r2vf[rid]["freq"].append(row["frequency"] * row["catcharea"])
        r2fd = {
            self.top.rid_to_rin[r]: PFD(vf["val"], vf["freq"], rm_zero_bins=False)
            for r, vf in r2vf.items()
        }
        cur.close()

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
            # fd.rm_small_bins(binthres, None)
            fd.relative()
            fd.cumulative()
            fd.freqs[-1] = 1  # it should be, but force incase not

        for ind, fd in r2fd.items():
            # topnet needs to have a 0 bin at the start, so if there isn't one
            # make it
            if fd.freqs[0] != 0:
                n = len(fd.bins) + 1
                self.v2val["numelev"][ind] = n
                self.v2val["elevval"][ind, :n] = [0] + [b[1] for b in fd.bins]
                self.v2val["elevfrq"][ind, :n] = [0] + [i for i in fd.freqs]
            else:
                n = len(fd.bins)
                self.v2val["numelev"][ind] = n
                self.v2val["elevval"][ind, :n] = [b[1] for b in fd.bins]
                self.v2val["elevfrq"][ind, :n] = [i for i in fd.freqs]
