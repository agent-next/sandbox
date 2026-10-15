# Worker diagnostic fixture

`Worker_20260731-172150-utc.log` is a minimized, sanitized extract of the
[public log attached to actions/runner#4597](https://github.com/user-attachments/files/30598992/Worker_20260731-172150-utc.log),
from runner 2.336.0. Generate it with `python generate.py <downloaded-log>`.
The generator retains the actual message envelope and context encoding, removes
all other data and replaces the repository, run, attempt, job and SHA.

Verified against actions/runner source at
`796cc18ffaaafd5cea525d6231f5a8c93c11c603`:

- [Worker.cs, line 101](https://github.com/actions/runner/blob/796cc18ffaaafd5cea525d6231f5a8c93c11c603/src/Runner.Worker/Worker.cs#L101)
  logs `Job message:\n {StringUtil.ConvertToJson(jobMessage)}`.
- [PipelineContextDataJsonConverter.cs, lines 150–170](https://github.com/actions/runner/blob/796cc18ffaaafd5cea525d6231f5a8c93c11c603/src/Sdk/DTPipelines/Pipelines/ContextData/PipelineContextDataJsonConverter.cs#L150-L170)
  serializes dictionaries as `{"t":2,"d":[{"k":key,"v":value}]}` and
  [lines 121–123](https://github.com/actions/runner/blob/796cc18ffaaafd5cea525d6231f5a8c93c11c603/src/Sdk/DTPipelines/Pipelines/ContextData/PipelineContextDataJsonConverter.cs#L121-L123)
  write string values directly.
- In the original log, lines 380–423 contain
  `contextData.github.d` entries for `repository`, `run_id` and `run_attempt`.
  Lines 296–298 contain `variables["system.github.job"].value`.
  [ExecutionContext.cs, lines 1028–1034](https://github.com/actions/runner/blob/796cc18ffaaafd5cea525d6231f5a8c93c11c603/src/Runner.Worker/ExecutionContext.cs#L1028-L1034)
  adds that variable as `github.job` *after* the job message is logged.
