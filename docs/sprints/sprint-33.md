# Sprint 33 — Causal Setup Detection

Status: implementation in progress. [Issue 246](https://github.com/krunaldodiya/SwingTradingAIAssistant/issues/246),
milestone 25, Project In Progress, High priority/risk, Story.
Owner/risk owner: Krunal Dodiya. [Plan 47](../plans/47-causal-setup-detection.md)
owns the bounded contract, finite signal-phase checklist and ordered gaps.

## Validation and authority

October 3 owner-authorized fresh chat planning and implementation. Latest owner
instruction excludes every issue marked Future, including indirect scope reuse.
Five open Future issues were observed and excluded. No Future issue was changed.
Plan 34, current architecture and delivered Structure/Price Action/Volume/
Relative Strength/context contracts govern discovery. October 2 exhaustive
docs report and targeted recovered Hindsight export are history/context only.
No key/passphrase file was read and no recovery service installed.

Sprint 32 was revalidated live: PR 245 merged as
`08501889ef7aacab93ac58409209fbe46dfaed10`; main admission 37029767889 success
on that merge, Issue 244 closed, Project Done, milestone 24 closed with no open
issues. Local main/origin main equal that merge. This is retained hosted proof,
not a rerun of 6,323 tests. Clean retained Sprint 32 checkout was advanced by a
new branch `codex/sprint33-causal-setup` from origin/main; no worktree deletion.

## Execution ownership

Goal created and verified ACTIVE after Issue/Project/milestone/contract freeze.
Owner explicitly reaffirmed continuous autonomous Goal use in this chat.
Coordinator native Codex `/root` is sole writer. Model/effort inherited; actual
host telemetry not exposed. Existing Python 3.11.16 `.venv` reused; no installation.
Two fresh read-only independent domain and security/provenance reviewers will
inspect the same clean committed candidate after all focused checks. No nested
delegation. No review, full coverage, installed, hosted, merge or release pass
is claimed yet. Protected effects retain scoped authority requirements.

## First implementation evidence

Actual CLI red: a valid `setup-screen-current` request failed because the command
was missing and the producer was not called. Invalid selections already failed
through the existing parser; they were not claimed as a discriminating red.
Initial command/SDK routing green: five checks passed. An accidentally configured
focused coverage run passed four input checks but failed total coverage at
19.64%; this was not full-suite or acceptance evidence. Subsequent repair feedback
uses explicit no-coverage/no-cache selection and does not weaken the final gate.

Independent synthetic 21-bar expectations establish latest UP BOS at position
20, prior UPTREND, high pivot 16 confirmed at 18. Real synthetic producer admission
through actual CLI returned MATCH/NO_MATCH/UNKNOWN for the three requested stocks;
the test forbade hidden-directory creation and passed. It retained current
acquisition/knowledge time and exposed no raw bars/prices/private paths. It
proves admission/projection, not real provider availability or trading usefulness.

Sixteen of an initial seventeen focused checks passed. The failed expectation
incorrectly treated a newly confirmed pivot as reason to suppress a valid break
of an older pivot. The corrected causal test requires pivot 10, confirmed at 12,
instead of using the pivot at 18 confirmed at 20; original failed result retained.
Two separate red adversaries exposed unsafe storage/unbounded diagnostics being
projected as UNKNOWN. The projection now stops those as terminal errors with no
JSON. The current focused run passed all 19 checks in 4.64 seconds, including
the corrected causal anchor and both diagnostic/storage discriminators.

Manifest refresh initially exposed a dependency cycle when the new manifest
bound a producer manifest which transitively bound it. The new manifest instead
binds the producer source; producer-owned manifests still validate its evidence
closure. Active CLI-bound manifests include the new projection and its manifest.
887 source bindings were independently hashed and verified after convergence.
New source file mode 0664 initially failed the existing runtime verifier; setting
the owned sources to normal 0644 resolved it without weakening the verifier.
Source-specific Pyright with the correct existing interpreter returned zero
errors/warnings. An earlier ad hoc tests-inclusive invocation used a different
interpreter and reported missing pytest/type issues; it is not a final gate.

## Remaining acceptance

Latest focused checkpoint: 45 tests passed in 12.65 seconds using the existing
interpreter with coverage and cache explicitly disabled for repair feedback.
Envelope-runtime and envelope-knowledge-time substitution adversaries exposed
two admission gaps; the projection now checks the verified producer runtime and
the admitted source knowledge time. Diagnostic failure fixtures use the correct
producer runtime so they exercise diagnostic/storage rejection itself.
The actual synthetic demonstration returned MATCH (exit 0), NO_MATCH (exit 0),
and UNKNOWN (exit 1) for positive, negative and insufficient scenarios.
Its audit guard prohibits network access and hidden-directory creation. Focused
Ruff checks and formatting passed for the demonstration and new test module.
These results are repair feedback, not full-suite or release acceptance.

Compatibility checkpoint: 20 of 21 existing single-stock/comparison demo checks
passed initially; the sole failure was the comparison's previous expected
identity. Base and candidate source were run independently with network and
hidden-directory denial. Canonical observation and comparison hashes were
recomputed independently: only observation runtime bindings changed; the admitted
packets, market facts, timing and comparison runtime were byte-equivalent.
The three expected comparison/observation hashes were updated from that proof.
All five comparison demonstration checks then passed in 5.06 seconds.
Evidence and capture helper are retained in
`/home/krunaldodiya/Documents/Codex/2026-10-03/sprint33-evidence/`, including
`base-comparison.json`, `candidate-comparison.json` and
`comparison-identity-reconstruction.txt`. No installation was used.

Review-preparation checkpoint: all 72 focused checks passed in 36.16 seconds
(45 setup, 16 existing single-stock, five comparison and six new setup-demo
checks). The demo guard probes confirmed both socket-family denial and denial
before hidden-directory creation. Ruff passed and all 373 selected source/test/
demo files were formatted. Existing-interpreter Pyright reported zero errors and
warnings; configured Vulture source check passed. The final manifest audit
verified all 887 bindings with no further changes. Complete focused output,
Pyright, Vulture and manifest receipts are retained in the visible evidence
directory above. Full coverage, package/installed and hosted gates remain pending.

Both complete independent full reviews of candidate
`a4f03049dd1aca4d22920efbac121d45d62775b7` (tree
`c5de273515d463e56bede41ef3427713f0da9c2a`) returned BLOCKERS. Domain and
security independently reproduced unknown-row knowledge-time substitution;
security also reproduced alphabet-safe arbitrary diagnostic disclosure. Both
reviewers remained read-only and verified clean exact bytes. Complete reports
`domain-review-a4f0304.md` and `security-review-a4f0304.md` are retained in the
visible evidence directory. Their 51 passing focused checks did not invalidate
the counterexamples, and neither verdict transfers to corrected bytes.

Correction regressions reproduced five failures and one already-correct
insufficient-structure rejection before repair (`review-correction-red.txt`).
Projection now admits the producer's closed stage/code/status/packet combinations
and validates the observed-coverage-derived envelope knowledge time before any
missing-evidence return. Packetless results require no source knowledge time.
No new mathematics, provider, persistence or attestation mechanism was added.
All 57 setup/demo checks then passed in 20.00 seconds
(`review-correction-green.txt`). Corrected comparison identities were recomputed
from captured observations; packets/facts/timing still match base bytes
(`corrected-comparison-identity-reconstruction.txt`). Broader focused/static
compatibility and new exact-current independent verdicts remain required.
The corrected combined focused run passed all 78 checks in 36.82 seconds
(`correction-focused-tests.txt`); Ruff/format, existing-interpreter Pyright and
configured Vulture passed. Final audit verified 887 bindings without changes.
Full coverage/build/installed/hosted gates and exact-current reviews remain pending.

Complete every Plan 47 matrix row, stable static/focused compatibility checks,
actual synthetic public demonstration and runtime identity reconstruction where
existing expected hashes move. Freeze a committed clean exact candidate, obtain
both independent full-slice reviews, consolidate any blockers, then complete
applicable full/build/installed/hosted gates with required effect authority.
Preserve truthful tracker/PR/main admission state and separate merge approval.
No lifecycle, expiry, eligibility or effectiveness completion follows from this
first detection slice; broader signal-phase gaps remain visible in Plan 47.
