import logging
from var_collection import VarCollection


class Topo(VarCollection):
    """
    Reach network connectivity

    Important concepts
    ------------------

    * reaches and aggregates.  When order == 1 they are one and the same.
      When order > 1 an aggregate is made up of one or more reaches.

    * indices and ids.  A reach id is generally a number in the millions
    and identifies a reach.  An aggregate id is the reach id of the most
    downstream reach in the aggregate.  We often use rid and aid variable
    names for reach and aggregate ids.  An index is simply a whole number.
    If there are 3 reaches in the network, the reach indices will be 0, 1,
    and 2.  Often use rin and ain for reach and aggregate indices.

    Attributes
    ----------

    rids: list
        reach index to reach id

    aids: list
        agg index to agg id.  When order == 1, aids == rids

    rid_to_rin: dict
        reach id to reach index.  Just rids reversed

    aid_to_ain: dict
        agg id to agg index.  Just aids reversed

    rin_to_ain: list
        reach index to agg index.  When order == 1, [0, 1, ...]

    ain_to_rins: list
        agg index to list of reach indices.  When order == 1,
        [[0], [1], ...]

    rin_to_ds: list
        reach index to downstream reach index

    ain_to_ds: list
        agg index to downstream agg index (or None)

    ain_to_ups: list
        agg index to list of upstream agg indices (or [])

    rin_to_ups: list
        reach index to list of upstream reach indices (or [])

    rin_to_sig: list
        reach index to bool indicating if significant

    __rin_to_blue: list
        reach index to bool indicating if blue

    Dimensions
    ----------

    Two dimensions are defined by this class
        nrch_noagg
            The number of reaches, len(rids)
        nrch
            Number of aggregates, len(aids)
    When order is 1 nrch_noagg == nrch, when order > 1 nrch_noagg >= nrch


    Variables
    --------

    This class defines a lot of variables, the definitions of such can be
    found in attr_info.jinja, but a summary is provided here.  The
    dimension is in parenthesis

    blue(nrch_noagg)
        1 if non aggregated reach is blue (required to make connected network)

    nonaggrch_nrch(nrch, maxe)
        For each agg, a list of reach indices in that agg

    nonaggrch_rchid(nrch, maxe)
        For each agg, a list of rid in that agg

    nrch_agg(nrch_noagg)
        The agg index for each reach

    numnonaggrch(nrch)
        The number of reachs in each aggregate

    numuprch(nrch)
        The number of upstream agg reaches

    rchid(nrch)
        The aggregate id

    rchid_agg(nrch_noagg)
        The agg id for each reach

    rchid_noagg(nrch_noagg)
        The reach id for each reach

    rchindex(nrch)
        [0, 1, 2, ... nrch_noagg-1]

    uprch_nrch(nrch, maxup)
        For each agg, a list of immediate upstream agg indices (so probably
        zero or two, sometimes three)

    uprch_rchid(nrch, maxup)
        For each agg, a list of immediate upstream agg ids
    """

    def __init__(self, attrs, outfile, con, truncates, a2info, r2info):
        self.truncates = truncates
        self.a2info = a2info
        self.r2info = r2info
        # we dont have topo defined, just pass None, it isn't needed
        super(Topo, self).__init__(attrs, outfile, con, None)

    def preamble(self):
        a2info = self.a2info
        r2info = self.r2info

        logging.info("Calculating connectivity attributes")

        self.rids = [r for info in a2info.values() for r in info["rids"]]
        self.aids = list(a2info.keys())

        self.rid_to_rin = {rid: rin for rin, rid in enumerate(self.rids)}
        self.aid_to_ain = {aid: ain for ain, aid in enumerate(self.aids)}

        self.ain_to_rins = [
            [self.rid_to_rin[r] for r in a2info[aid]["rids"]] for aid in self.aids
        ]

        self.rin_to_ain = list(range(len(self.rids)))
        for ain, rins in enumerate(self.ain_to_rins):
            for rin in rins:
                self.rin_to_ain[rin] = ain

        self.rin_to_ds = [
            self.rid_to_rin[r2info[rid]["down"]] if r2info[rid]["down"] else None
            for rid in self.rids
        ]

        self.ain_to_ds = [
            self.aid_to_ain[a2info[aid]["down"]] if a2info[aid]["down"] else None
            for aid in self.aids
        ]

        self.ain_to_ups = [
            [self.aid_to_ain[u] for u in a2info[aid]["ups"]] for aid in self.aids
        ]

        self.rin_to_ups = [
            [self.rid_to_rin[u] for u in r2info[rid]["ups"]] for rid in self.rids
        ]

        self.rin_to_sig = [r2info[rid]["sig"] for rid in self.rids]
        self.__rin_to_blue = [r2info[rid]["blue"] for rid in self.rids]

        ######################################################################
        self.attrs.update({"nrch": len(self.aids)})
        self.attrs.update({"nrch_noagg": len(self.rids)})
        self.setup_dim("nrch", len(self.aids))
        self.setup_dim("nrch_noagg", len(self.rids))

    def dfn_vars(self):
        self.v2val["blue"][:] = self.__rin_to_blue

        # for each agg downstream ain
        self.v2val["dsrch_nrch"][:] = [
            i if i is not None else self.v2info["dsrch_nrch"]["fillvalue"]
            for i in self.ain_to_ds
        ]
        self.v2info["dsrch_nrch"]["attributes"]["valid_max"] = len(self.aids)

        # for each agg downstream aid
        self.v2val["dsrch_rchid"][:] = [
            self.aids[i] if i is not None else self.v2info["dsrch_rchid"]["fillvalue"]
            for i in self.ain_to_ds
        ]
        self.v2info["dsrch_rchid"]["attributes"]["valid_min"] = min(self.aids)
        self.v2info["dsrch_rchid"]["attributes"]["valid_max"] = max(self.aids)

        # for each agg, a list of rin in that agg
        for ain, rins in enumerate(self.ain_to_rins):
            self.v2val["nonaggrch_nrch"][ain, : len(rins)] = rins

        # for each agg, a list of rid in that agg
        for ain, rs in enumerate(self.ain_to_rins):
            self.v2val["nonaggrch_rchid"][ain, : len(rs)] = [self.rids[r] for r in rs]

        # the ain for each reach
        self.v2val["nrch_agg"][:] = self.rin_to_ain
        self.v2info["nrch_agg"]["attributes"]["valid_max"] = len(self.aids)

        # number of reachs in each aggregate
        self.v2val["numnonaggrch"][:] = list(map(len, self.ain_to_rins))

        # the number of upstream agg reaches
        self.v2val["numuprch"][:] = list(map(len, self.ain_to_ups))

        # rchid(nrch)
        self.v2val["rchid"][:] = self.aids
        self.v2info["rchid"]["attributes"]["valid_min"] = min(self.aids)
        self.v2info["rchid"]["attributes"]["valid_max"] = max(self.aids)

        # aid for each reach
        self.v2val["rchid_agg"][:] = [self.aids[ain] for ain in self.rin_to_ain]

        # rid for each reach
        self.v2val["rchid_noagg"][:] = self.rids

        # rchindex(nrch)
        self.v2val["rchindex"][:] = list(range(len(self.aids)))
        self.v2info["rchindex"]["attributes"]["valid_max"] = len(self.aids)

        # for each agg, a list of upstream agg indices
        for ain, ups in enumerate(self.ain_to_ups):
            self.v2val["uprch_nrch"][ain, : len(ups)] = ups
        self.v2info["uprch_nrch"]["attributes"]["valid_max"] = len(self.aids)

        # for each agg, a list of upstream agg ids
        for ain, ups in enumerate(self.ain_to_ups):
            self.v2val["uprch_rchid"][ain, : len(ups)] = [self.aids[u] for u in ups]
        self.v2info["uprch_rchid"]["attributes"]["valid_min"] = min(self.aids)
        self.v2info["uprch_rchid"]["attributes"]["valid_max"] = max(self.aids)
