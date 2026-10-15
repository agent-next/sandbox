# orders

A tiny sqlite-backed order service: storage (`orders/store.py`), pagination
(`orders/pagination.py`), configuration (`orders/config.py`) and a job
worker (`orders/worker.py`). Pure Python, standard library only.

    python -m pytest -q
