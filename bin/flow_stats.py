import logging
import psycopg2.extras
from var_collection import VarCollection


class FlowStats(VarCollection):
    """Flow stats variables qm, qm_error, q100 and 100_error"""

    def dfn_vars(self):
        # whn order==1 aids is same as rids. limits the sql query
        allreaches = ",".join(map(str, self.top.aids))

        q = f"""
           SELECT reach.rchid, reach.lowerreach,
            (flowstats.q_a_0_8*pow(reach.accarea/1000000.0, 0.8))::Int8 AS qm,
            (
                0.22*flowstats.q_a_0_8*pow(reach.accarea/1000000.0, 0.8)
            )::Int8 AS qm_error,
            (                                                                                                                   
                flowstats.q_a_0_8*pow(                                                                                     
                    reach.accarea/1000000.0, 0.8                                       
                )*flowstats.q100                                                       
            )::Int8 AS q100,                                                            
            (
                0.28*flowstats.q_a_0_8*pow(reach.accarea/1000000.0, 0.8)*flowstats.q100
            )::Int8 AS q100_error,
            0.1 AS rch_minflow
            FROM reach, flowstats
            WHERE
                reach.rchid = flowstats.rchid AND 
                reach.rchid IN ({allreaches}) AND
                reach.catcharea > 0 AND
                reach.accarea > 0 AND
                flowstats.q100 > 0 AND
                flowstats.q_a_0_8 > 0
            ORDER BY reach.accarea DESC
        """
        logging.debug(f"Flow stats query {q}")
        cur = self.con.cursor(cursor_factory=psycopg2.extras.DictCursor)
        cur.execute(q)
        logging.info(f"Flow stats for {cur.rowcount} reaches")
        for row in cur.fetchall():
            ri = self.top.aid_to_ain[row["rchid"]]
            for var, val in self.v2val.items():
                val[ri] = row[var]
        cur.close()
