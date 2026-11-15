"""Determinism conventions, applied at the start of every command.

Sets the timezone to UTC, seeds the stdlib and numpy global generators, and
exports `PYTHONHASHSEED` so child processes (parser workers) hash the same way.
New code should take randomness from `rng(seed)`, a seeded
`numpy.random.Generator`, and record the seed in the run manifest.
"""

import os
import random
import time

import numpy as np

DEFAULT_SEED = 0


def apply(seed: int = DEFAULT_SEED) -> None:
    os.environ["TZ"] = "UTC"
    if hasattr(time, "tzset"):
        time.tzset()
    # Only affects processes started from here on (workers), not this one.
    os.environ["PYTHONHASHSEED"] = str(seed)
    random.seed(seed)
    np.random.seed(seed)


def rng(seed: int) -> np.random.Generator:
    return np.random.default_rng(seed)
