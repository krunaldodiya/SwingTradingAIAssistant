# Data downloader future TODO

These items do not block downloader v1, research-module implementation, or the
Sprint 3 completion gate. Promote an item into an approved later epic only when
there is a demonstrated product need and a short implementation specification.

## Distribution and interfaces

- Publish the package to PyPI through Trusted Publishing (ARK-39). Local wheel
  build and clean-install proof remain sufficient for downloader-v1 acceptance.
- Add API or MCP transports only for a real consumer. They must wrap the same
  versioned application contracts and may not create a second calculation path.

## Derived views

- Add weekly and monthly session-aware derived views if a research module needs
  them. They must be computed locally from verified canonical data with zero
  extra historical-provider requests.

## Provider breadth

- Evaluate an additional market-data provider only for a measured reliability,
  licensing, coverage, or continuity need. Keep provider details behind the
  existing vendor-independent boundary.

## Optimization

- Perform further performance tuning only after retained benchmarks identify a
  material bottleneck. Preserve bounded memory, concurrency, retries, queues,
  timeouts, output, and reproducible before/after evidence.

## Explicit non-goals

- Do not expand the downloader to derivatives, forex, crypto, broker execution,
  or unrelated instruments under this TODO. Such work requires a separate owner-
  approved product direction.
