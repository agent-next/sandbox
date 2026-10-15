# Dataset provenance

`mbpp_subset.jsonl` — 30 pinned MBPP problems (task_id 11..40, first 30
tasks of the upstream `test` split whose reference solutions pass all
their own tests), derived from:

- Source: HuggingFace `google-research-datasets/mbpp` (the official MBPP
  mirror; the original `google-research-datasets/mbpp` GitHub repo hosts
  the same data), file `full/test-00000-of-00001.parquet`
- Pinned at revision `4bb6404fdc6cacfda99d4ac4205087b89d32030c`
  (`https://huggingface.co/datasets/google-research-datasets/mbpp/resolve/<sha>/full/test-00000-of-00001.parquet`,
  sha256 `566fd53060ffba5766dace1d1e2f4c38906781526de222b0dfbdbc325b696c77`,
  115 824 bytes)
- Licence: CC-BY-4.0, as published with the MBPP dataset (Chen et al.,
  2021, arXiv:2107.03374, "Evaluating Large Language Models Trained on
  Code")
- Each line is one JSON object with `task_id`, `text`, `code`,
  `test_setup_code` (empty for all 30), `test_list` (≤ 3 assertions).
  Every `code` reference solution passes every assertion in its
  `test_list` (verified, see `judge/setup.sh` step 3).

`judge/setup.sh` does not re-download or regenerate this file: the subset
is committed, and setup verifies its sha256 (`judge/dataset-sha256.txt`)
before use so a regenerator that changed even one byte would fail loudly.
