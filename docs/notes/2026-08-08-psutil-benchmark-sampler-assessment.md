# psutil benchmark sampler assessment

Date: 2026-08-08
Status: accepted

## Context

ARK-90 needs a test-only parent-process sampler for the Plan 03 B01 benchmark
child. The sampler observes only the child process RSS and open file-descriptor
count under the frozen READY/START/DONE/EXIT protocol; it does not alter the
production ingestion path, provider behavior, or persisted market data.

## Assessment and decision

`psutil==7.2.2` is accepted as an exact development/test dependency. At the
time of assessment, PyPI metadata reported BSD-3-Clause licensing,
`Requires-Python >=3.6`, supported macOS wheel artifacts, and the process RSS
and `num_fds()` APIs required by Plan 03. The official GitHub repository
security-advisory API returned no published advisory, and an OSV query for the
exact PyPI package/version returned no vulnerability record.

The exact pin and its registry hashes are retained in `pyproject.toml` and
`uv.lock`. This assessment does not approve a production runtime dependency,
host/user/path collection, provider calls, or any performance threshold claim.

## Residual risk

Process metrics are local observations and can vary with operating-system and
background load. Unsupported FD sampling or any sampler exception is explicit
`INVALID` blocked resource evidence, never a partial pass. Reassess the pin
before a future dependency upgrade or any expansion beyond test instrumentation.

## References

- [psutil 7.2.2 PyPI metadata](https://pypi.org/pypi/psutil/7.2.2/json)
- [psutil security advisories](https://github.com/giampaolo/psutil/security/advisories)
- [OSV query API](https://api.osv.dev/v1/query)
