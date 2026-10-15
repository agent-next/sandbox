# Runner stats API recordings

These fixtures were recorded with `cli/scripts/record_runner_stats.py`, not
constructed by hand. They cover a completed mixed-runner run, a failed run
with skipped steps, and a cancelled run. The mixed run's latest attempt is
16. The script uses five jobs per page so pagination is exercised by real
responses.

To record from a repository you can read:

```bash
python cli/scripts/record_runner_stats.py --repo OWNER/REPO --run ID \
  --output cli/tests/fixtures/runner_stats/mixed.json
```

Pass `--serve-log serve.jsonl` to also record real lifecycle events for those
jobs. The mixed fixture includes these events, with only runner aliases,
event types and timing fields retained.

Each recording contains its timestamp, API version and hashes of the raw
in-memory responses. Names and IDs are replaced and labels are allowlisted
before saving. Timing, status, conclusion and step numbers remain exactly
as the API returned them. No raw response or credential is saved.

Tests use these recordings as timing oracles. Edge-case tests explicitly
modify copies (missing timestamps, size labels, runner prefixes and live
status), rather than presenting synthetic data as an API recording.

## Deviations and measurement limits

- VM sizes are not available from the jobs API. The report labels its
  `--size` assumption and can use explicit size labels instead.
- Cost estimates include job runtime only. Hosted vCPU usage and cost are
  unknown, not inferred from `ubuntu-latest`.
- Lifecycle joins require an existing serve log; absent phases remain
  unknown. No sandbox is created to collect stats.
- The GitHub run search caps results at 1,000; larger windows fail with a
  request to narrow `--since`, rather than returning partial summaries.
