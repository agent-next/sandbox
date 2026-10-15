"""Runtime configuration for the order service."""

import json
import os

DEFAULTS = {
    "db_path": ":memory:",
    "page_size": 20,
    "retry_limit": 3,
}


def load_config(path=None):
    """Return the service configuration.

    Values in the JSON file at ``path`` override ``DEFAULTS``.  When ``path``
    is not given the ``ORDERS_CONFIG`` environment variable is used; when
    neither is set, only the defaults apply.
    """
    if path is None:
        path = os.environ.get("ORDERS_CONFIG")
    if path is None:
        return dict(DEFAULTS)
    with open(path, encoding="utf-8") as handle:
        loaded = json.load(handle)
    config = dict(DEFAULTS)
    config.update(loaded)
    return config
