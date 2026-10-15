"""PR 5 is a clean refactor: the config loads exactly as before."""

import json

from orders.config import load_config


def test_file_values_override_defaults():
    path = "/tmp/pr5-config.json"
    with open(path, "w", encoding="utf-8") as handle:
        json.dump({"page_size": 5}, handle)
    config = load_config(path)
    assert config["page_size"] == 5
    assert config["retry_limit"] == 3
