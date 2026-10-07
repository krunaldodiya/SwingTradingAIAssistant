# Plan64: retained stock observation and comparison workflow

Accepted October7,2026 under [Issue290](https://github.com/krunaldodiya/SwingTradingAIAssistant/issues/290)
and the owner's instruction to start the combined usable workflow. R3 owner
Krunal Dodiya. Base `0bba1769619cad7c6159c986e8c42c690f04d3b7`.
Implementation, instructions and qualification are one delivery; preparation
alone closes no Plan61 outcome. The Issue owns all eight acceptance criteria,
file ownership, complete adversarial matrix and release/effect boundaries.

## Question and least adequate correction

Can a supported stock's original current research observation be revisited in
a later execution and compared with another exact observation, preserving what
was actually known? Existing price revisions, schedules and mapping evidence
are retained; the complete original producer request/result association is not.
Current result JSON omits source bars and is not admitted typed input. The
existing comparison CLI requires an injected observation service.

Selected: a minimal immutable private record referencing existing admitted
evidence plus the exact original public result; readback validates references,
rebuilds through the existing producers and requires original-byte equality.
This is the least adequate G05 correction. No generic archive, arbitrary JSON
import, replay framework, fresh historical acquisition or new provider.

## First working contract

`stock-observations observe --symbol SYMBOL --storage-root ABSOLUTE_ROOT
--question PRICE_BEHAVIOR|CURRENT_STRUCTURE --output json [--refresh]`
calls the existing actual-current V2 producer with its real system clock and
existing source contracts. There is no historical clock/date/session override.
After source acquisition, it validates the typed observation and durably
publishes one canonical `observation-record@v1` object under the existing
owner-private root. Only successful publication returns its 64-hex SHA256
handle. The original research result is included without source bars. Research
unavailability/insufficiency remains distinct from record-publication failure.

`stock-observations read --storage-root ABSOLUTE_ROOT --observation SHA256
--output json` selects the exact immutable object, admits the original mapping
from a read-only catalog and retained snapshot, reads each exact capture
revision and rebuilds its packet/result. All original source, request, mapping,
selection, deadline, known-time, revision and result bytes must agree. No source
fetch, evidence/catalog write, latest substitution or timestamp relabeling.
Lease/temporary read-only catalog resources retain existing governed effects.

`stock-observations compare --storage-root ABSOLUTE_ROOT --previous SHA256
--current SHA256 --output json` reads two explicit records and invokes the
unchanged `current-stock-observation-comparison@v1` core. Output binds both
record handles and the existing complete comparison. All stock, question,
basis, chronology, availability and fact-delta rules remain unchanged.

Public envelopes use `stock-observations@v1`; copied JSON/hash is not admission.
Malformed requests return exit2/redacted request_invalid with no source effect.
Read/storage/version/source refusal returns exit1 and a sanitized explicit
unavailable envelope. Research NOT_READY/UNAVAILABLE/INSUFFICIENT_EVIDENCE or
NON_COMPARABLE remains exit1 with its typed result; complete READY or COMPARABLE
is exit0. Help is available without source or storage access. No raw OHLCV,
credentials, private root or exception text is emitted.

## Integrity, bounds and compatibility

One supported stock/question per record, one selected record per read, exactly
two per comparison. Handles are lowercase64hex; canonical JSON maximum4MiB,
nesting maximum64; duplicate/extra keys and noncanonical/malformed values fail
closed. Existing snapshot/catalog/capture/session/lineage bounds remain.
No record directory enumeration. Observe is the only writer. Reuse the existing
exclusive root lease, private directory and immutable publication mechanisms;
files400/directories700, no symlink/hardlink/overwrite or storage escape.
Interrupted publication remains unavailable; exact retry is idempotent and
conflicting bytes refuse. Corrections create a separate observation handle;
the earlier selected record is never replaced or read through a latest pointer.

Records support only this explicit version and the admitted current research
runtime. Unknown/old incompatible versions refuse without mutation; no automatic
upgrade or migration. Existing capture predecessor readers retain their exact
compatibility. The first delivery preserves old producers/calculations and all
historical records. Existing prior wheel/runtime recovery remains required.

## Frozen falsifying matrix and ownership

Issue290 freezes positive exact round trips for both questions; partial/terminal
availability; changed/unchanged/newly unavailable facts; request/schema/size/
nesting bounds and limit-plus-one; source/mapping/revision/time/runtime
substitution; temporal order/same session; correction/retry/missing baseline;
combined-failure precedence; unsafe root/path/mode/ownership/lease/races;
publication interruption/recovery; no network or evidence/catalog writes on
read/compare; installed/OCI identity and historical compatibility/recovery.
Root is the only writer and integration owner. Independent domain and privacy/
security/provenance reviewers inspect the clean committed full candidate and
own only distinct private report files; neither delegates or changes candidate.
Both full current verdicts and all applicable existing release gates are required.

## Actual evidence and later work

Synthetic retained producers can qualify deterministic behavior and installed
paths. Actual-source readback is a separate observed claim. The existing pair
contract requires strictly increasing selection, completed-session and
known-times; two same-session live acquisitions do not qualify a pair.
An actual newly recorded baseline must precede an actual later completed-session
observation unless independently admitted earlier evidence already exists.
If the source/window is unavailable, name that exact claim and earliest valid
observation while continuing independent software verification and delivery.
No baseline is fabricated or backdated. G05/G08 close only on their full Plan61
evidence; software delivery alone does not close either or the product.

The owner accepted four delivery groups: practical research (G05/G08 and the
descriptive portion of G10); supported safety/policy/analytical decisions
(G03/G04/G07); complete suggestions/qualification (G06/G09 and final G10);
paper observation and phase audit (G11/G12). These organize related tasks,
not four promised sprints. Original outcome dependencies/closure predicates,
all eight Plan47 obligations and five Future exclusions remain intact.
No eligibility/expiry/scoring/AI destination/strategy/capital/portfolio changes.
