# -*- coding: utf-8 -*-
"""
Network utilities

NAME
    utils

METHODS

    def terms(con, start: int, end: int) -> list
        Return terminal reaches in [start, end)

    def agg_up(con, rid: int, order: int, extras=set([]), truncates=[])
        Trace/aggregate upstream from rid

    def aggid_for_rid(con, rid: int, order: int) -> int
        Return the aggregate reach ID for given reach
"""

import psycopg2
import logging
import numpy as np
from collections import Counter


def terms(con, start: int, end: int) -> list:
    """Return terminal reaches in [start, end)"""

    cur = con.cursor()
    q = f"""
        SELECT rchid
        FROM reach
        WHERE lowerreach = 0 AND {start} <= rchid AND rchid < {end}
    """
    cur.execute(q)
    logging.debug(f"Terms query {q}")
    return [i[0] for i in cur.fetchall()]


def agg_up(con, rid: int, order: int, extras=set([]), truncates=[]):
    """Trace/aggregate upstream from rid

    Parameters
    ----------
    con: psycopg2.extensions.connection

    rid: int
        Start from this reach ID

    order: int
        Aggregate to this order

    extras: list
        Always break at these reaches (probably contain lakes and/or sites)

    truncates: list
        A list of reaches that we will block further tracing, we will
        include reaches just below these

    Returns
    -------
    dict:
        {
            'agg': {
                aid0: {
                    'down': down aid or None
                    'ups': list of upstream aid or [],
                    'rids': list of reaches inside this aggregate
                },
                ...
            },
            'reach': {
                rid0: {
                    'down': down rid or None
                    'ups': list of upstream rid or [],
                    'agg': aid this reach is in,
                    'sig': bool,
                    'blue': bool
                },
                ...
            }
        }
        The 'agg' dict gives the aggregate info, the 'reach' dict gives info
        for each individual reach.  The 'sig' key indicates if the reach is
        significant, one thing this can be used for is calculating the
        llength_all variable.  The 'blue' key indicates this reach is needed to
        make a connected network.  Note all sigs are blue, there just might be
        some extra reaches that are required to join the aggs together, so not
        all blues are sigs.  Eg aggregating to order 3 with an aggregate with
        order 3, 2 and 2 reaches, and on the end of one of the order 2s are
        some order 1s but one is a lake so a new agg is formed there.
    """

    cond = f" AND tab.rchid NOT IN ({','.join(map(str, truncates))})" if truncates else ""

    # do the trace
    cur = con.cursor(cursor_factory=psycopg2.extras.DictCursor)
    q = f"""
        WITH RECURSIVE tree AS (
          SELECT rchid, lowerreach as down, streamorder >= {order} as sig
          FROM reach
          WHERE rchid={rid}

        UNION ALL

          SELECT
            tab.rchid, tab.lowerreach as down, tab.streamorder >= {order} as sig
          FROM reach as tab
          JOIN tree ON tab.lowerreach = tree.rchid {cond}
        )
        SELECT * FROM tree
    """
    logging.debug(f"Trace up query {q}")
    cur.execute(q)
    logging.debug(f"Trace up from {rid}, got {cur.rowcount} rows")

    r2info = {
        r["rchid"]: {
            "aid": r["rchid"],
            "sig": r["sig"],
            "blue": r["sig"],
            "down": r["down"],
            "ups": [],
        }
        for r in cur.fetchall()
    }
    # make sure the most downstream has no downstream
    r2info[rid]["down"] = None

    # fill in ups using the down
    for r, info in r2info.items():
        if info["down"] is not None:
            r2info[info["down"]]["ups"].append(r)

    # if order one, rids is just aid, and done
    if order == 1:
        a2info = {
            r: {"down": info["down"], "ups": info["ups"], "rids": [r]}
            for r, info in r2info.items()
        }
        return {"agg": a2info, "reach": r2info}

    # if rchid in extras, then it AND its siblings are significant
    if extras:
        for r, info in r2info.items():
            if r not in extras:
                continue
            info["sig"] = True
            if not (dw := info["down"]):
                continue
            for u in r2info[dw]["ups"]:
                r2info[u]["sig"] = True

    # list of downs that have upstream sigs (has repeats)
    sigs = [info["down"] for r, info in r2info.items() if info["sig"]]

    # the down for extras with no siblings will only appear in sigs once, which
    # isn't enough for r2nsig[d] > 1, so force in an extra sig
    sigs += [info["down"] for r, info in r2info.items() if r in extras]

    # r2nsig maps rid to number of upstream significant reaches
    r2nsig = Counter(sigs)

    # ensure that the first reach is considered a new aggregate by setting its
    # downstream (which is None) to have a count of 2.
    r2nsig[None] = 2

    # if my downstream has > 1 sig then make new aid (ie my aid is me)
    # otherwise set my aid to my downstreams aid
    for r, info in r2info.items():
        if r2nsig[info["down"]] > 1:
            # make a new agg
            info["aid"] = r
            # better be sig (might not be if 3 siblings and we aren't sig)
            info["sig"] = True
        else:
            info["aid"] = r2info[info["down"]]["aid"]

    # create the aggregate dict ###########################
    a2info = {}
    for rid, info in r2info.items():
        a2info.setdefault(info["aid"], {"rids": [], "ups": []})["rids"].append(rid)

    # connect the aggs together via down
    for aid, info in a2info.items():
        # the reach just below the agg reach, get its agg
        rid = r2info[aid]["down"]
        info["down"] = r2info[rid]["aid"] if rid else None

    for aid, info in a2info.items():
        if info["down"]:
            a2info[info["down"]]["ups"].append(aid)
    ######################################################

    # finally, ensure that below a sig reach is blue
    for info in r2info.values():
        info["blue"] = info["sig"]
    for info in r2info.values():
        if info["down"] and info["blue"]:
            r2info[info["down"]]["blue"] = True

    return {"agg": a2info, "reach": r2info}


def aggid_for_rid(con, rid: int, order: int, extras: list) -> int:
    """Return the aggregate reach ID for given reach

    A trace downstream is performed to find the bottom of the current
    aggregate.  extras contains sites and/or lakes, possibly empty if not
    breaking at these locations.

    Parameters
    ----------
    con: psycopg2.extensions.connection

    rid: int
        The reach ID to find aggregate ID for

    order: int
        2 to 9

    extras: list
        Possibly empty list of reaches where the network should be broken

    Returns
    -------
    int
        the aggregate reach ID down stream.  rid is in this aggregate.
    """

    if order == 1 or rid in extras:
        return rid

    # if extras need this condition to stop tracing down
    cond = (
        f"""
            (
                SELECT count(*)
                FROM reach
                WHERE lowerreach = tab.rchid AND rchid IN ({",".join(map(str, extras))})
            ) AS break
        """
        if extras
        else "0 as break"
    )

    cur = con.cursor()

    # go down stream using 'lowerreach', until we are at a branch that has more than
    # one significant reach, or at a lake/site break
    # start with tree, joining tree.lowerreach to tab.rchid
    # cnt is the number of significant _siblings_ to tab.rchid == tree.lowerreach
    # break is the number of _siblings_ that are in extras
    cur.execute(
        f"""
        WITH RECURSIVE tree AS (

            SELECT rchid, lowerreach
            FROM reach
            WHERE rchid = {rid}

            UNION ALL

            SELECT rchid, lowerreach
            FROM (
                SELECT tab.rchid, tab.lowerreach, {cond},
                    (
                        SELECT count(*)
                        FROM reach
                        WHERE lowerreach = tab.rchid AND streamorder >= {order}
                    ) AS cnt
                FROM reach AS tab
                JOIN tree ON tab.rchid = tree.lowerreach
            ) AS t
            WHERE t.cnt <= 1 and t.break < 1
        ) SELECT * FROM tree;
    """
    )
    ret = cur.fetchall()

    if ret:  # pylint: disable=no-else-return
        # travelled all the way to aggregate reach
        return ret[-1][0]
    else:
        raise ValueError(f"Reach {rid} doesn't exist in reach table")


class PositiveFreqDistribution:
    """A continuous frequency distribution with left hand bin starting at zero"""

    def __init__(self, bins: list, freqs: list, rm_zero_bins: bool = True):
        """A continuous frequency distribution defined by right side of bin

        Eg for the distribution

            0 < x <= 3    5
            3 < x <= 3.5  8

        pass in bins = [3, 3.5], totals = [5, 8].

        Notes:
        1. The rec2cdf code would use bins = [0, 3, 3.5] and totals = [0, 5, 8]
           which is unneccessary, but OK to do since we just strip off leading
           zeros.
        2. Repeated bins/freqs are treated as extra info to be combined.  Eg
           bins = [3, 3.5, 3.5] and totals = [1, 2, 3] doesn't result in
            0 < x <= 3    1
            3 < x <= 3.5  2
           which you might since that last bin is [3.5, 3.5), instead it results in
            0 < x <= 3    1
            3 < x <= 3.5  5

        Parameters
        ----------
        bins: list
            A list of right-hand-side bin boundaries.  Assumed to be sorted

        totals: list
            A list of total values in each bin.  len(totals) == len(bins)

        rm_zero_bins: bool
            If true then remove bins that have zero freq
        """
        assert len(bins) == len(freqs)
        assert sorted(bins) == bins
        assert all(b >= 0 for b in bins)
        assert all(f >= 0 for f in freqs)

        # remove leading zeros
        start = next((i for i, x in enumerate(bins) if x != 0), None)
        if start:
            bins = bins[start:]
            freqs = freqs[start:]

        # add frequencies for repeated bins
        if len(set(bins)) != len(bins):
            i = 0
            while i < len(bins) - 1:
                if bins[i] == bins[i + 1]:
                    freqs[i] += freqs[i + 1]
                    del bins[i + 1]
                    del freqs[i + 1]
                    i -= 1  # check again incase multiple dups
                i += 1

        # remove bins with freq == 0
        if rm_zero_bins:
            bf = [(b, f) for b, f in zip(bins, freqs) if f != 0]
            bins = [i[0] for i in bf]
            freqs = [i[1] for i in bf]
            assert len(bins) > 0
        self.rm_zero_bins = rm_zero_bins  # handy if we combine this pfd

        # make the bins
        #   (0, x)  f0
        #   (x, y)  f1
        #   (y, z)  f2
        self.bins = [(0, bins[0])]
        for i in range(len(bins) - 1):
            self.bins.append((bins[i], bins[i + 1]))

        self.freqs = freqs

    def relative(self):
        """Convert to relative fd."""
        s = sum(self.freqs)
        self.freqs = [f / s for f in self.freqs]
        return self

    def cumulative(self):
        """Convert to cumulative fd."""
        self.freqs = list(np.cumsum(self.freqs))
        return self

    def set_max_bin(self, max_rhs):
        """Remove all bins bigger than max_rhs, but leave at least one bin

        Eg. suppose we have:
            (0, 1)   2
            (1, 3)   5
            (3, 3.5) 6
            (3.5, 5) 3
        and max_rhs = 3.25 then we change to
            (0, 1)    2
            (1, 3)    5
            (3, 3.25) 9

        Parameters:
        -----------
        max_rhs: float
            Must be > 0.  Bins larger than max_rhs are thrown away, and their
            contents added to the new last bin
        """

        assert max_rhs > 0

        # find last bin we will keep
        ind = next((i for i, b in enumerate(self.bins) if max_rhs <= b[1]), None)
        if ind is None:
            return

        self.bins[ind] = (self.bins[ind][0], max_rhs)
        self.freqs[ind] = sum(f for f in self.freqs[ind:])
        self.bins = self.bins[: (ind + 1)]
        self.freqs = self.freqs[: (ind + 1)]

    def freq_in_slow(self, bin):
        """Return the frequency value in this bin.  This is to support
        new_bins_slow which we don't use anymore.

        Eg: suppose our fd is
            0 < x <= 3    5
            3 < x <= 3.5  8
        then
            freq_in((0, 0)) = 0
            freq_in((0, 1)) = 5/3
            freq_in((2, 3)) = 5/3
            freq_in((3, 10)) = 7/(1/2) * 8
            freq_in((3.5, 4)) = 0
            freq_in((2, 4)) = 5/3+8
            freq_in((-2, 1)) = 5/3
            freq_in((-2, 3.25)) = 5 + 8/2

        Parameters:
        -----------
        (left, right): (float, float)
            A bin (left, right]

        Returns:
        --------
        float:
            The frequency in this bin assuming current frequencies are uniform
            in their bins.
        """

        assert 0 <= bin[0] <= bin[1]

        # find how much each bin intersects with (bin[0], bin[1]]
        ints = [(min(bin[1], b[1]) - max(bin[0], b[0])) / (b[1] - b[0]) for b in self.bins]
        # negative intersections are zero
        ints = [i if i >= 0 else 0 for i in ints]

        # sum up frequencies
        return sum(frac * freq for frac, freq in zip(ints, self.freqs))

    def new_bins_slow(self, bins):
        """Re-calculate the distribution on new bins.  This is slow and not
        used anymore, we use rebin_jhykes

        Parameters
        ----------
        bins: list
            A sorted list of right-hand-side bin boundaries.  Will redistribute
            on these boundaries
        """
        self.freqs = [self.freq_in_slow(b) for b in bins]
        self.bins = bins

    def rebin_jhykes(self, bins):
        """Return new freqs on the given bins

        For speed purposes bins, self.bins, and self.freqs are assumed to be
        np.arrays.  Also bins and self.bins must be flat lists containing just
        the boundaries, unlike the usual tuples.

        Parameters
        ----------
        bins: np.array
            These are the bin boundaries as a list.  The usual bins in this
            class are stored as tuples (l0, r0), (l1, r1), (ln, rn) etc.  This
            routine takes (l0, l1, l2, ... rn)
        """

        # the fractional bin locations of the new bins in the old bins
        i_place = np.interp(bins, self.bins, np.arange(len(self.bins)))

        cum_sum = np.r_[[0], np.cumsum(self.freqs)]

        # calculate bins where lower and upper bin edges span
        # greater than or equal to one original bin.
        # This is the contribution from the 'intact' bins (not including the
        # fractional start and end parts.
        whole_bins = np.floor(i_place[1:]) - np.ceil(i_place[:-1]) >= 1.0
        start = cum_sum[np.ceil(i_place[:-1]).astype(int)]
        finish = cum_sum[np.floor(i_place[1:]).astype(int)]

        newf = np.where(whole_bins, finish - start, 0.0)

        bin_loc = np.clip(np.floor(i_place).astype(int), 0, len(self.freqs) - 1)

        # fractional contribution for bins where the new bin edges are in the same
        # original bin.
        same_cell = np.floor(i_place[1:]) == np.floor(i_place[:-1])
        frac = i_place[1:] - i_place[:-1]
        contrib = frac * self.freqs[bin_loc[:-1]]
        newf += np.where(same_cell, contrib, 0.0)

        # fractional contribution for bins where the left and right bin edges are in
        # different original bins.
        different_cell = np.floor(i_place[1:]) > np.floor(i_place[:-1])
        frac_left = np.ceil(i_place[:-1]) - i_place[:-1]
        contrib = frac_left * self.freqs[bin_loc[:-1]]

        frac_right = i_place[1:] - np.floor(i_place[1:])
        contrib += frac_right * self.freqs[bin_loc[1:]]

        newf += np.where(different_cell, contrib, 0.0)

        return newf

    @classmethod
    def combine_slow(cls, pfds):
        """Make one pfd from a list of them using the slow methods

        The finest bins are used to combine all the distributions

        Eg:
            (0, 1)   2
            (1, 3)   5
            (3, 3.5) 6
            (3.5, 5) 3
            (5, 7)   8
        and
            (0, 0.5) 3
            (0.5, 2) 2
            (2, 4.5) 5
        combine to
            (0, 0.5)    1 + 3
            (0.5, 1)    1 + 2/3
            (1, 2)      5/2 + 4/3
            (2, 3)      5/2 + 5*1/2.5
            (3, 3.5)    6 + 5*0.5/2.5
            (3.5, 4.5)  3*2/3 + 5*1/2.5
            (4.5, 5)    3*1/3 + 0
            (5, 7)      8

        Parameters
        ----------
        pfds: list
            A list of PositiveFreqDistributions

        Returns
        -------
        PositiveFreqDistribution
            The combination of all the distributions
        """
        if len(pfds) == 0:
            return None
        elif len(pfds) == 1:
            return pfds[0]

        # get the new bins
        bins = [b[0] for p in pfds for b in p.bins] + [b[1] for p in pfds for b in p.bins]
        bins = sorted(set(bins))
        bins = [(bins[i], bins[i + 1]) for i in range(len(bins) - 1)]

        # convert each pfd onto new bins
        for p in pfds:
            p.new_bins_slow(bins)

        # now can just add each frequency
        freqs = [sum(p.freqs[i] for p in pfds) for i in range(len(bins))]

        return cls([b[1] for b in bins], freqs, rm_zero_bins=all(i.rm_zero_bins for i in pfds))

    @classmethod
    def combine(cls, pfds):
        """Make one pfd from a list of them

        The finest bins are used to combine all the distributions

        Eg:
            (0, 1)   2
            (1, 3)   5
            (3, 3.5) 6
            (3.5, 5) 3
            (5, 7)   8
        and
            (0, 0.5) 3
            (0.5, 2) 2
            (2, 4.5) 5
        combine to
            (0, 0.5)    1 + 3
            (0.5, 1)    1 + 2/3
            (1, 2)      5/2 + 4/3
            (2, 3)      5/2 + 5*1/2.5
            (3, 3.5)    6 + 5*0.5/2.5
            (3.5, 4.5)  3*2/3 + 5*1/2.5
            (4.5, 5)    3*1/3 + 0
            (5, 7)      8

        Parameters
        ----------
        pfds: list
            A list of PositiveFreqDistributions

        Returns
        -------
        PositiveFreqDistribution
            The combination of all the distributions
        """
        if len(pfds) == 0:
            return None
        elif len(pfds) == 1:
            return pfds[0]

        # for speed purposes flatten bins in pfds and make np.arrays
        for p in pfds:
            p.bins = np.array([b[0] for b in p.bins] + [p.bins[-1][1]])
            p.freqs = np.array(p.freqs)

        # new bins are the old bins sorted and dups removed, gives finest bins
        bins = np.unique(np.concatenate([p.bins for p in pfds]))

        # get new freqs over the new bins, then sum them
        newfreqs = np.array([p.rebin_jhykes(bins) for p in pfds])
        newfreqs = newfreqs.sum(axis=0).tolist()

        return cls(bins[1:].tolist(), newfreqs, rm_zero_bins=all(i.rm_zero_bins for i in pfds))

    def rm_small_bins(self, maxw, maxf):
        """Combine bins narrower than maxw and shorter than maxf neighbour

        Parameters:
        -----------
        maxw: float
        maxf: float or None
            Any bin narrower than maxw and (if maxf) shorter than maxf will be
            combined with bin to the right.  If maxf is None then we only
            compare the width to maxw.
        """

        def is_small(i):
            if maxf is None:
                return self.bins[i][1] - self.bins[i][0] < maxw
            return (self.bins[i][1] - self.bins[i][0] < maxw) and self.freqs[i] < maxf

        # can't do anything without at least two bins
        if len(self.bins) < 2:
            return

        # collapse narrow bins into bin to the right
        i = 0
        while i < len(self.bins) - 1:
            if is_small(i):
                self.bins[i] = (self.bins[i][0], self.bins[i + 1][1])
                self.freqs[i] += self.freqs[i + 1]
                del self.bins[i + 1]
                del self.freqs[i + 1]
                i -= 1  # check again incase multiple small bins
            i += 1

        # if only one bin left, this is as much as we can do
        if len(self.bins) < 2:
            return

        # check the last bin, if it is narrow collapse to the previous
        if is_small(-1):
            self.bins[-2] = (self.bins[-2][0], self.bins[-1][1])
            self.freqs[-2] += self.freqs[-1]
            del self.bins[-1]
            del self.freqs[-1]

    def __str__(self):
        return "\n".join(f"({b[0]}, {b[1]}) {f}" for b, f in zip(self.bins, self.freqs))
