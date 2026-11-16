"""Determinism conventions (spec 0001, Determinism conventions row)."""

import os
import random
import time

import numpy as np

from parsebench import determinism


def test_apply_sets_timezone_to_utc(monkeypatch):
    monkeypatch.setenv("TZ", "Asia/Kolkata")

    determinism.apply()

    assert os.environ["TZ"] == "UTC"
    if hasattr(time, "tzset"):
        assert time.localtime(0).tm_hour == 0
        assert time.strftime("%Z", time.localtime(0)) == "UTC"


def test_apply_exports_hash_seed_for_child_processes():
    determinism.apply(seed=123)

    assert os.environ["PYTHONHASHSEED"] == "123"


def test_apply_uses_seed_zero_by_default():
    determinism.apply()

    assert os.environ["PYTHONHASHSEED"] == "0"


def test_apply_makes_stdlib_random_repeatable():
    determinism.apply(seed=7)
    first = [random.random() for _ in range(5)]

    determinism.apply(seed=7)
    second = [random.random() for _ in range(5)]

    assert first == second


def test_apply_makes_numpy_global_random_repeatable():
    determinism.apply(seed=7)
    first = np.random.random(5)

    determinism.apply(seed=7)
    second = np.random.random(5)

    np.testing.assert_array_equal(first, second)


def test_rng_with_same_seed_gives_same_stream():
    a = determinism.rng(42).random(10)
    b = determinism.rng(42).random(10)

    np.testing.assert_array_equal(a, b)


def test_rng_with_different_seeds_gives_different_streams():
    a = determinism.rng(1).random(10)
    b = determinism.rng(2).random(10)

    assert not np.array_equal(a, b)


def test_rng_returns_a_numpy_generator():
    assert isinstance(determinism.rng(0), np.random.Generator)


def test_rng_is_independent_of_global_seeding():
    determinism.apply(seed=1)
    a = determinism.rng(42).random(3)

    determinism.apply(seed=999)
    b = determinism.rng(42).random(3)

    np.testing.assert_array_equal(a, b)
