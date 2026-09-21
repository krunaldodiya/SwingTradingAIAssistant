# Issue #190 reproducible raw public-workflow measurement

Status: baseline protocol and harness archive; candidate verification pending.

The accompanying [baseline record](2026-09-21-current-workflow-baseline.json)
binds the original files by SHA-256. The source blocks below preserve those
worker and sampler bytes. They are offline measurement utilities, not production
entrypoints, tests automatically selected by pytest, or live provider scripts.

## Reproduction

Use the repository's declared development dependencies in the recorded Python
3.13.7/macOS environment for comparable observations. Check out the recorded
baseline revision for before measurements or the exact reviewed candidate for
after measurements. Save the worker and sampler blocks as `baseline_worker.py`
and `baseline_runner.py` together in a fresh output directory. Change only the
worker's `ROOT` assignment to the absolute checkout being measured. The worker
explicitly imports that checkout and its fixture helpers. Report this path-only
adaptation and the resulting source digest. Retain the original digests; never
claim adapted files have the original byte identity.

Use a fresh output directory because the sampler refuses to overwrite previous
runs. Invoke `measure(n, repetition)` from the sampler using the same interpreter;
one process per invocation. Run repetition 0 as discarded warmup and 1–3 as
measured observations, serially. Baseline N2 supplemental repetitions 4–6 are
an explicitly recorded variance investigation, not replacements for repetitions
1–3. The sampler's original command-line default includes the costly N50 baseline;
do not rerun that cancelled series merely to reconstruct the already-retained
incomplete observation. Candidate N50 completion remains required.

The original sampler has no wall-time termination mechanism. Candidate execution
must monitor each public-call stage against the frozen ceiling and preserve any
interrupted attempt as failed/incomplete. Do not silently let the fixed logical
clock stand in for a real-time limit. No benchmark is run by reading this file.

## Frozen original protocol

# Raw V2 baseline protocol — frozen before repeated measurements

Revision b3465a9695d7f1d8f6284f8f375ccade51917684; no production changes. Coordinator owns these temporary raw harness files. Independent BharatStock measurement has separate ownership and is serialized with these repeats to avoid resource contention.

Public research_current_price_context_v2; synthetic Luhn-valid distinct canonical equities; full 375-minute sessions; September2026 fixture calendar covering required monthly plan; 21 completed sessions / 7,875 minutes per member plus 15 current minutes. Calendar-only initial root; mapping acquired by mock wire; no owner data or credentials. Cohorts N=1 and N=50. Synthetic calendar is test data, not asserted exchange evidence. Actual network denied. No new provider or profile.

For each cohort, one discarded warmup process then three measured fresh processes. Each process performs cold ACQUIRE_MISSING, RETAINED_ONLY warm, then identical-prefix REFRESH_ONCE. Setup separately timed. Logical selection clock fixed; wall clock perf_counter measures actual public call through typed return. TTFI equals return time for this synchronous API. Serialize workloads. Each result must retain full ordered cohort, OBSERVED completed/current states, exact consumed wire replies, canonical decoder roundtrip, truthful measured attempt counts. Expected cold 3N+1, retained0, refreshN; no retries/pagination. Pagination is not applicable. Capture exact request/admission settings from public result.

External parent psutil samples child RSS every20ms during public-call start/end events; retain process-wide and per-call sampled peaks, start RSS, sample count and maximum sample gap. Import/setup are included only in process-wide peak. Sampling and subprocess/event overhead are explicit; sub20ms spikes may be missed. Wall timing excludes serialization of result and parent sampling. Results are local offline orchestration cost, never provider network latency or production SLA. Report median, min/max and range/median; >20% variation requires investigation before optimization conclusions. No numeric performance acceptance budgets are chosen until these baseline observations exist; no optimization yet.

The nominal7875-minute workload does not prove the10000-minute limit or all three-month distributions. Existing boundary contracts/tests remain required; add distinct boundary workload only where necessary for a claim. A 50-member cohort is measured whole, not by combining smaller cohorts. Profile an observed hotspot after baseline; maximum two targeted optimization experiments before re-evaluating benefit. Preserve fixture shapes and measurement boundary for before/after comparison.

Exploratory probe preceding this protocol:1-member cold9.999s/4attempts, retained2.952s/0, refresh8.382s/1. Not a repeated baseline or budget. Earlier probe failed private-root admission under system /var temporary-path alias; preserved as setup failure, corrected by using canonical /private/tmp. No product repair or gate weakening.

## Pre-implementation amendments

# Adaptive measurement bound, before optimization

Status: accepted coordinator measurement decision; no production edit yet.

The original N50 discarded cold warmup was interrupted after21m04s with50
price partitions and9 action records, while still CPU-active. Its overlapping
capture/profiling and partial evidence remain preserved in n50-censored-stop.json
and the raw/resources/error records. No typed whole-cohort result completed.
This is not a successful baseline, median, provider timeout or production failure.
The original plan for three additional N50 baseline repetitions is superseded.

Retain the completed three-repetition N1 baseline. Complete one warmup plus
three measured N2 repetitions with the identical375-minute/21-session fixture,
entry-to-return boundary and externalRSS sampler, serialized without other task
measurements. These establish completed multi-member cold/retained/refresh
baselines and variance before budgets/implementation. Source limits remain1–50;
N2 does not prove N50 throughput. Freeze numeric N1/N2 budgets and an explicit
N50 candidate ceiling before any implementation. The candidate must complete
whole N50 calls with all canonical members, original exact semantics and counts.
Any N50 comparison is limited by the incomplete, noisy pre-change observation;
never invent a completed before value, median or percentage improvement.

This narrows repetition cost, not accepted cohort behavior or final correctness,
review, coverage, build or hosted gates. No CI or test suite was cancelled.

## N2 variance investigation, before budgets or optimization

All original N2 runs exited successfully. Measured cold/retained/refresh medians
were 21.656 / 5.116 / 19.519 seconds; range/median was 1.99% / 2.85% /
21.61%. Refresh repetition 2 took 23.304 seconds versus 19.086 and 19.519.
The >20% protocol threshold requires investigation. RSS sampling gaps reached
74 ms for refresh; this does not establish the cause of the slower sample.
No sample is discarded or relabelled. Run exactly three supplemental fresh
N2 processes (repetitions 4–6), unchanged worker/environment, serialized. Keep
the original and supplemental series separately and report pooled observations
without selecting the faster series. This is one bounded variability check,
not an optimization experiment or a repeated full suite. If variability remains,
carry uncertainty explicitly into budgets and require improvements exceeding it;
do not repeat indefinitely to obtain a desired result.

## Original worker

```python
"""Frozen offline public-path baseline worker; no production optimization."""
import json
import socket
import sys
import tempfile
import time
from dataclasses import replace
from datetime import UTC, date, datetime, timedelta
from pathlib import Path

ROOT = Path('/Users/krunaldodiya/WorkSpace/Code/SwingTradingAIAssistant-issue190')
sys.path[:0] = [str(ROOT / 'src'), str(ROOT / 'tests/market_data')]
import pytest
from current_raw_acquisition_fixtures import (
    FixtureTokenProvider, FixedClock, RecordedWire, WireReply, action_body,
    current_month_schedule, mapping_body, request, seed_root,
)
import swing_trading_ai_assistant.market_data.current_raw_acquisition as acquisition
import swing_trading_ai_assistant.market_data.current_raw_acquisition_transport as transport
from swing_trading_ai_assistant.market_data.current_raw_price_context import (
    CurrentPriceContextMemberV1, is_valid_current_price_context_isin_v1,
)
from swing_trading_ai_assistant.research_packet import current_price_context_v2 as api


def deny(*args, **kwargs):
    raise AssertionError('actual network forbidden in offline baseline')


def candles(sessions, last_minutes=None):
    rows = []
    for session in sessions:
        count = int((session.close_at - session.open_at).total_seconds() // 60)
        if last_minutes is not None:
            count = last_minutes
        for minute in range(count):
            close = 100 + minute / 1000
            rows.append([(session.open_at + timedelta(minutes=minute)).isoformat(),
                         close, close + 1, close - 1, close, 10, None])
    return json.dumps({'status': 'success', 'data': {'candles': rows}}).encode(), len(rows)


def run(n):
    selection = datetime(2026, 9, 30, 4, 0, 30, tzinfo=UTC)
    schedule = current_month_schedule(selection)
    schedule = replace(schedule, sessions=tuple(
        replace(s, close_at=s.open_at + timedelta(minutes=375)) for s in schedule.sessions))
    members = []
    for i in range(n):
        stem = f'INE{i:03d}A0100'
        isin = next(stem + str(d) for d in range(10)
                    if is_valid_current_price_context_isin_v1(stem + str(d)))
        members.append(CurrentPriceContextMemberV1(isin, 'NSE', 'EQUITY', 'EQ',
                       f'FIX{i:03d}', date(2020, 1, 1), date(2030, 1, 1)))
    raw = request(schedule, selection=selection, members=tuple(members))
    history, history_rows = candles(tuple(s for s in schedule.sessions if s.trade_date < date(2026, 9, 30)))
    intraday, current_rows = candles((schedule.sessions[-1],), 15)
    questions = ('RAW_MARKET_STRUCTURE', 'RAW_20_SESSION_DIRECTION',
                 'RAW_COHORT_BREADTH', 'RAW_INDUSTRY_PARTICIPATION')
    records = []
    with tempfile.TemporaryDirectory(prefix='issue190-offline-', dir='/private/tmp') as td, pytest.MonkeyPatch.context() as patch:
        patch.setattr(socket.socket, 'connect', deny)
        patch.setattr(socket, 'create_connection', deny)
        patch.setattr(acquisition, 'EnvironmentAccessTokenProvider', FixtureTokenProvider)
        root = Path(td) / 'root'
        started = time.perf_counter()
        seed_root(root, schedule_value=schedule, request_value=raw, retain_mapping=False)
        setup = time.perf_counter() - started
        for mode in ('ACQUIRE_MISSING', 'RETAINED_ONLY', 'REFRESH_ONCE'):
            replies = []
            if mode == 'ACQUIRE_MISSING':
                replies = ([WireReply(body=mapping_body(tuple(members)))] +
                           [WireReply(body=history) for _ in members] +
                           [WireReply(body=action_body()) for _ in members] +
                           [WireReply(body=intraday) for _ in members])
            elif mode == 'REFRESH_ONCE':
                replies = [WireReply(body=intraday) for _ in members]
            payload_bytes = sum(len(reply.body) for reply in replies)
            wire = RecordedWire(replies)
            patch.setattr(transport, 'build_opener', wire.build_opener)
            req = api.CurrentPriceContextRequestV2('current-price-context-request@v2',
                  selection, raw.admission_deadline, raw.schedule_identity_sha256,
                  tuple(members), questions, None, mode, True)
            print(json.dumps({'event': 'start', 'mode': mode, 'n': n}), flush=True)
            started = time.perf_counter()
            result = api.research_current_price_context_v2(req, root, clock=FixedClock(selection))
            elapsed = time.perf_counter() - started
            print(json.dumps({'event': 'end', 'mode': mode, 'n': n}), flush=True)
            encoded = result.canonical_json_bytes()
            states = [x.state for x in result.completed_context.members]
            current = [x.state for x in result.current_session]
            api.current_price_context_result_from_canonical_json_bytes_v2(encoded)
            record = {'mode': mode, 'n': n, 'seconds': elapsed, 'ttfi_seconds': elapsed,
                      'setup_seconds': setup, 'history_rows_per_member': history_rows,
                      'current_rows_per_member': current_rows, 'attempts': wire.attempts,
                      'fixture_payload_bytes': payload_bytes, 'unused_replies': len(wire.replies), 'completed_states': states,
                      'current_states': current, 'result': json.loads(encoded)}
            records.append(record)
            print(json.dumps(record), flush=True)
            assert states == ['OBSERVED'] * n and current == ['OBSERVED'] * n
            assert not wire.replies
    return records


if __name__ == '__main__':
    run(int(sys.argv[1]) if len(sys.argv) > 1 else 1)
```

## Original external RSS sampler

```python
"""Serialize offline workers and sample their RSS from the parent process."""
import hashlib
import json
import os
import platform
import select
import subprocess
import sys
import time
from pathlib import Path

import psutil

HERE = Path(__file__).resolve().parent
WORKER = HERE / 'baseline_worker.py'


def measure(n, repetition):
    output = HERE / f'n{n}-rep{repetition}.jsonl'
    errors = HERE / f'n{n}-rep{repetition}.stderr'
    assert not output.exists(), 'preserve existing observations; use a new result directory'
    peaks = {}
    active = None
    pending = b''
    total_peak = 0
    last_sample = None
    with output.open('wb') as log, errors.open('wb') as err:
        child = subprocess.Popen([sys.executable, str(WORKER), str(n)], stdout=subprocess.PIPE, stderr=err)
        process = psutil.Process(child.pid)
        assert child.stdout is not None
        fd = child.stdout.fileno()
        eof = False
        while not eof:
            now = time.perf_counter()
            try:
                rss = process.memory_info().rss
                total_peak = max(total_peak, rss)
                if active is not None:
                    item = peaks[active]
                    item['peak_rss_bytes'] = max(item['peak_rss_bytes'], rss)
                    item['samples'] += 1
                    if last_sample is not None:
                        item['max_sample_gap_seconds'] = max(item['max_sample_gap_seconds'], now-last_sample)
                    last_sample = now
            except psutil.NoSuchProcess:
                pass
            ready, _, _ = select.select([fd], [], [], .02)
            if not ready:
                continue
            chunk = os.read(fd, 65536)
            if not chunk:
                eof = True
                continue
            log.write(chunk)
            log.flush()
            pending += chunk
            while b'\n' in pending:
                line, pending = pending.split(b'\n', 1)
                value = json.loads(line)
                if value.get('event') == 'start':
                    active = value['mode']
                    peaks[active] = {'start_rss_bytes': rss, 'peak_rss_bytes': rss,
                                     'samples': 0, 'max_sample_gap_seconds': 0}
                    last_sample = None
                elif value.get('event') == 'end':
                    active = None
                else:
                    print(json.dumps({k:value[k] for k in ('mode','n','seconds','attempts')}), flush=True)
        code = child.wait()
    receipt = {'n':n, 'repetition':repetition, 'warmup':repetition==0, 'exit_code':code,
               'process_peak_rss_bytes':total_peak, 'public_call_rss':peaks,
               'platform':platform.platform(), 'python':sys.version,
               'worker_sha256':hashlib.sha256(WORKER.read_bytes()).hexdigest()}
    (HERE / f'n{n}-rep{repetition}-resources.json').write_text(json.dumps(receipt,indent=2)+'\n')
    assert code == 0, f'worker failed; inspect {errors}'


if __name__ == '__main__':
    for count in (1, 50):
        for repeat in range(4):
            measure(count, repeat)
```
