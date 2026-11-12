"""Fixture for SFL-007 — a failed parse is handed back to the caller as a value.

The `except` deletes the reason nothing was read, and `cfg` is still returned, so
"could not read the config" arrives at the caller as "the config".
"""

import json


def load_config(path):
    try:
        cfg = json.load(open(path))
    except OSError:
        pass
    return cfg
