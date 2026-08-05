# -*- coding: utf-8 -*-

import pytest
from utils import PositiveFreqDistribution as PFD


def test_bins_not_nonneg():
    with pytest.raises(AssertionError):
        PFD([-1, 0, 2], [1, 2, 3])


def test_freqs_not_nonneg():
    with pytest.raises(AssertionError):
        PFD([0, 0, 2], [1, -2, 3])


def test_bins_not_sorted():
    with pytest.raises(AssertionError):
        PFD([2, 1], [1, 2])


def test_bins_and_freq_length_mismatch():
    with pytest.raises(AssertionError):
        PFD([1, 2, 3], [1, 2])


def test_freq_in_slow_neg_left():
    d = PFD([3, 3.5], [5, 8])
    with pytest.raises(AssertionError):
        d.freq_in_slow((-2, 3))


def test_no_bins():
    with pytest.raises(AssertionError):
        PFD([], [])


def test_zero_freqs():
    d = PFD([3, 3.5, 5], [5, 0, 8])
    assert d.bins == [(0, 3), (3, 5)]
    assert d.freqs == [5, 8]
    with pytest.raises(AssertionError):
        PFD([3, 3.5, 5], [0, 0, 0])

    d = PFD([3, 3.5, 5], [5, 0, 8], rm_zero_bins=False)
    assert d.bins == [(0, 3), (3, 3.5), (3.5, 5)]
    assert d.freqs == [5, 0, 8]


def test_freq_in_slow_right_smaller_than_left():
    d = PFD([3, 3.5], [5, 8])
    with pytest.raises(AssertionError):
        d.freq_in_slow((2, 1))


def test_leading_zeros():
    d = PFD([0, 3, 3.5], [7, 5, 8])
    assert d.bins == [(0, 3), (3, 3.5)]
    assert d.freqs == [5, 8]
    d = PFD([0, 0, 3, 3.5], [77, 7, 5, 8])
    assert d.bins == [(0, 3), (3, 3.5)]
    assert d.freqs == [5, 8]


def test_repeated_bins():
    d = PFD([0, 3, 3, 3.5], [7, 5, 2, 8])
    assert d.bins == [(0, 3), (3, 3.5)]
    assert d.freqs == [7, 8]
    d = PFD([3, 3, 3.5, 3.5, 3.5, 5], [7, 5, 2, 3, 11, 8])
    assert d.bins == [(0, 3), (3, 3.5), (3.5, 5)]
    assert d.freqs == [12, 16, 8]


def test_freq_in_slow():
    d = PFD([3, 3.5], [5, 8])
    assert d.freq_in_slow((0, 0)) == pytest.approx(0)
    assert d.freq_in_slow((0, 1)) == pytest.approx(5 / 3)
    assert d.freq_in_slow((2, 3)) == pytest.approx(5 / 3)
    assert d.freq_in_slow((3, 10)) == pytest.approx(8)
    assert d.freq_in_slow((3.5, 4)) == pytest.approx(0)
    assert d.freq_in_slow((2, 4)) == pytest.approx(5 / 3 + 8)
    assert d.freq_in_slow((0, 3.25)) == pytest.approx(5 + 8 / 2)


def test_relative():
    d = PFD([3, 3.5], [5, 8])
    d.relative()
    assert d.bins == [(0, 3), (3, 3.5)]
    assert d.freqs == [5 / 13, 8 / 13]


def test_cumulative():
    d = PFD([3, 3.5], [5, 8])
    d.cumulative()
    assert d.bins == [(0, 3), (3, 3.5)]
    assert d.freqs == [5, 13]


def test_new_bins_slow():
    d = PFD([3, 3.5, 8, 10], [5, 8, 3, 1])
    bins = [(0, 2), (2, 3), (3, 3.4), (3.4, 7), (7, 11)]
    d.new_bins_slow(bins)
    assert d.bins == bins
    assert d.freqs == pytest.approx(
        [5 * 2 / 3, 5 / 3, 0.8 * 8, 0.2 * 8 + 3 * 3.5 / 4.5, 3 / 4.5 + 1]
    )


def test_combine_slow():
    d0 = PFD([1, 3, 3.5, 5, 7], [2, 5, 6, 3, 8])
    d1 = PFD([0.5, 2, 4.5], [3, 2, 5])
    d2 = PFD.combine_slow([d0, d1])
    assert d2.bins == [
        (0, 0.5),
        (0.5, 1),
        (1, 2),
        (2, 3),
        (3, 3.5),
        (3.5, 4.5),
        (4.5, 5),
        (5, 7),
    ]
    assert d2.freqs == pytest.approx(
        [
            1 + 3,
            1 + 2 / 3,
            5 / 2 + 4 / 3,
            5 / 2 + 5 * 1 / 2.5,
            6 + 5 * 0.5 / 2.5,
            3 * 2 / 3 + 5 * 1 / 2.5,
            3 * 1 / 3 + 0,
            8,
        ]
    )


def test_combine_slow_zero_bins():
    d0 = PFD([1, 3, 3.5, 5, 7], [2, 5, 6, 0, 8], rm_zero_bins=False)
    d1 = PFD([0.5, 2, 4.5], [3, 2, 5])
    d2 = PFD.combine_slow([d0, d1])
    assert d2.bins == [
        (0, 0.5),
        (0.5, 1),
        (1, 2),
        (2, 3),
        (3, 3.5),
        (3.5, 4.5),
        (4.5, 5),
        (5, 7),
    ]
    assert d2.freqs == pytest.approx(
        [
            1 + 3,
            1 + 2 / 3,
            5 / 2 + 4 / 3,
            5 / 2 + 5 * 1 / 2.5,
            6 + 5 * 0.5 / 2.5,
            0 * 2 / 3 + 5 * 1 / 2.5,
            0 * 1 / 3 + 0,
            8,
        ]
    )


def test_combine():
    d0 = PFD([1, 3, 3.5, 5, 7], [2, 5, 6, 3, 8])
    d1 = PFD([0.5, 2, 4.5], [3, 2, 5])
    d2 = PFD.combine([d0, d1])
    assert d2.bins == [
        (0, 0.5),
        (0.5, 1),
        (1, 2),
        (2, 3),
        (3, 3.5),
        (3.5, 4.5),
        (4.5, 5),
        (5, 7),
    ]
    assert d2.freqs == pytest.approx(
        [
            1 + 3,
            1 + 2 / 3,
            5 / 2 + 4 / 3,
            5 / 2 + 5 * 1 / 2.5,
            6 + 5 * 0.5 / 2.5,
            3 * 2 / 3 + 5 * 1 / 2.5,
            3 * 1 / 3 + 0,
            8,
        ]
    )


def test_combine_zero_bins():
    d0 = PFD([1, 3, 3.5, 5, 7], [2, 5, 6, 0, 8], rm_zero_bins=False)
    d1 = PFD([0.5, 2, 4.5], [3, 2, 5])
    d2 = PFD.combine([d0, d1])
    assert d2.bins == [
        (0, 0.5),
        (0.5, 1),
        (1, 2),
        (2, 3),
        (3, 3.5),
        (3.5, 4.5),
        (4.5, 5),
        (5, 7),
    ]
    assert d2.freqs == pytest.approx(
        [
            1 + 3,
            1 + 2 / 3,
            5 / 2 + 4 / 3,
            5 / 2 + 5 * 1 / 2.5,
            6 + 5 * 0.5 / 2.5,
            0 * 2 / 3 + 5 * 1 / 2.5,
            0 * 1 / 3 + 0,
            8,
        ]
    )


def test_rm_small_narrow():
    d = PFD([0.5, 3, 3.5, 5, 7], [2, 5, 6, 3, 8])
    d.rm_small_bins(1 / 2, 0.0001)
    assert d.bins == [(0, 1 / 2), (1 / 2, 3), (3, 3.5), (3.5, 5), (5, 7)]
    assert d.freqs == [2, 5, 6, 3, 8]

    d = PFD([0.4, 3, 3.5, 5, 7], [0.2, 5, 6, 3, 8])
    d.rm_small_bins(1 / 2, 0.3)
    assert d.bins == [(0, 3), (3, 3.5), (3.5, 5), (5, 7)]
    assert d.freqs == [5.2, 6, 3, 8]

    d = PFD([0.4, 0.6, 3.5, 5, 7], [0.2, 1, 6, 3, 8])
    d.rm_small_bins(1 / 2, 0.4)
    assert d.bins == [(0, 0.6), (0.6, 3.5), (3.5, 5), (5, 7)]
    assert d.freqs == [1.2, 6, 3, 8]

    d = PFD([0.4, 0.45, 3.5, 5, 7], [0.2, 0.3, 6, 3, 8])
    d.rm_small_bins(0.5, 0.6)
    assert d.bins == [(0, 3.5), (3.5, 5), (5, 7)]
    assert d.freqs == [6.5, 3, 8]

    d = PFD([0.4, 2, 3.5, 5, 5.4], [0.2, 5, 6, 3, 0.08])
    d.rm_small_bins(0.5, 0.3)
    assert d.bins == [(0, 2), (2, 3.5), (3.5, 5.4)]
    assert d.freqs == [5.2, 6, 3.08]


def test_rm_small_short():
    d = PFD([0.5, 3, 3.5, 5, 7], [2, 5, 6, 0.3, 8])
    d.rm_small_bins(2, 0.5)
    assert d.bins == [(0, 0.5), (0.5, 3), (3, 3.5), (3.5, 7)]
    assert d.freqs == [2, 5, 6, 8.3]

    d = PFD([0.4, 3, 3.5, 5, 7], [0.2, 0.1, 6, 3, 8])
    d.rm_small_bins(4, 0.5)
    assert d.bins == [(0, 3.5), (3.5, 5), (5, 7)]
    assert d.freqs == [6.3, 3, 8]

    d = PFD([0.4, 0.6, 3.5, 5, 7], [0.02, 0.05, 0.06, 0.03, 0.08])
    d.rm_small_bins(7, 0.5)
    assert d.bins == [(0, 7)]
    assert d.freqs == [0.24]

    d = PFD([0.4, 0.45, 3.5, 5, 7], [0.2, 0.5, 6, 3, 8])
    d.rm_small_bins(0.5, 0.8)
    assert d.bins == [(0, 3.5), (3.5, 5), (5, 7)]
    assert d.freqs == [6.7, 3, 8]


def test_rm_small_justnarrow():
    d = PFD([0.5, 3, 3.5, 5, 7], [0.2, 5, 6, 3, 8])
    d.rm_small_bins(1 / 2, None)
    assert d.bins == [(0, 1 / 2), (1 / 2, 3), (3, 3.5), (3.5, 5), (5, 7)]
    assert d.freqs == [0.2, 5, 6, 3, 8]

    d = PFD([0.4, 3, 3.5, 5, 7], [0.2, 5, 6, 3, 8])
    d.rm_small_bins(1 / 2, None)
    assert d.bins == [(0, 3), (3, 3.5), (3.5, 5), (5, 7)]
    assert d.freqs == [5.2, 6, 3, 8]

    d = PFD([0.4, 0.6, 3.5, 5, 7], [0.2, 1, 6, 3, 8])
    d.rm_small_bins(1 / 2, None)
    assert d.bins == [(0, 0.6), (0.6, 3.5), (3.5, 5), (5, 7)]
    assert d.freqs == [1.2, 6, 3, 8]

    d = PFD([0.4, 0.45, 3.5, 5, 7], [0.2, 0.3, 6, 3, 8])
    d.rm_small_bins(0.5, None)
    assert d.bins == [(0, 3.5), (3.5, 5), (5, 7)]
    assert d.freqs == [6.5, 3, 8]

    d = PFD([0.4, 2, 3.5, 5, 5.4], [0.2, 5, 6, 3, 0.08])
    d.rm_small_bins(0.5, None)
    assert d.bins == [(0, 2), (2, 3.5), (3.5, 5.4)]
    assert d.freqs == [5.2, 6, 3.08]


def test_set_max_bin():
    d = PFD([0.5, 3, 3.5, 5, 7], [2, 5, 6, 0.3, 8])
    d.set_max_bin(7)
    assert d.bins == [(0, 0.5), (0.5, 3), (3, 3.5), (3.5, 5), (5, 7)]
    assert d.freqs == [2, 5, 6, 0.3, 8]

    d = PFD([0.5, 3, 3.5, 5, 7], [2, 5, 6, 0.3, 8])
    d.set_max_bin(7.5)
    assert d.bins == [(0, 0.5), (0.5, 3), (3, 3.5), (3.5, 5), (5, 7)]
    assert d.freqs == [2, 5, 6, 0.3, 8]

    d = PFD([0.5, 3, 3.5, 5, 7], [2, 5, 6, 0.3, 8])
    d.set_max_bin(6.5)
    assert d.bins == [(0, 0.5), (0.5, 3), (3, 3.5), (3.5, 5), (5, 6.5)]
    assert d.freqs == [2, 5, 6, 0.3, 8]

    d = PFD([0.5, 3, 3.5, 5, 7], [2, 5, 6, 0.3, 8])
    d.set_max_bin(1.5)
    assert d.bins == [(0, 0.5), (0.5, 1.5)]
    assert d.freqs == [2, 19.3]

    d = PFD([0.5, 3, 3.5, 5, 7], [2, 5, 6, 0.3, 8])
    d.set_max_bin(0.5)
    assert d.bins == [(0, 0.5)]
    assert d.freqs == [21.3]

    d = PFD([0.5, 3, 3.5, 5, 7], [2, 5, 6, 0.3, 8])
    d.set_max_bin(0.4)
    assert d.bins == [(0, 0.4)]
    assert d.freqs == [21.3]

    d = PFD([0.5, 3, 3.5, 5, 7], [2, 5, 6, 0.3, 8])
    with pytest.raises(AssertionError):
        d.set_max_bin(-0.1)
    with pytest.raises(AssertionError):
        d.set_max_bin(0)
