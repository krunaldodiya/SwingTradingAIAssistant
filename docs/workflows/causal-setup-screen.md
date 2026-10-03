# Causal Structure setup research screen

Sprint 33 / [Issue 246](https://github.com/krunaldodiya/SwingTradingAIAssistant/issues/246),
[Plan 47](../plans/47-causal-setup-detection.md). Implementation under verification.

The local command answers one fixed factual question: does each explicitly
supplied stock have an upward BOS on its latest admitted completed session?
It reuses the existing Structure producer, including pivot confirmation and
source admission. It does not calculate a retest or make a recommendation.

```sh
market-data setup-screen-current --symbol PNB --symbol RELIANCE \
  --storage-root /absolute/owner-private/research-root --output json
```

Use 1–10 distinct supported symbol inputs. The command may contact the existing
official calendar/mapping and BharatStock sources even without a refresh flag.
Before real use, establish exact source-acquisition, storage, credentials and
disclosure authority. It does not send output to an AI automatically. A local
coding assistant can use a remote model; local capture is not disclosure consent.

Read each row's canonical mapping, session, basis, source/capture/result identities,
selection and evidence-knowledge times, availability/support/comparability and
reason before explanation. MATCH is an observed latest-session upward BOS;
NO_MATCH is a supported Structure fact without that event; UNKNOWN includes
insufficient Structure or missing required evidence. Missing optional analytical
context does not suppress a supported detection. No verdict proves trade eligibility.

MATCH includes event and pivot identities and their sessions. The pivot's
confirmation precedes the event. These are descriptive references, not an entry
price, entry confirmation, active trade, invalidation or expiry policy. Identical
observations have stable identities; rolling windows/corrections can change them.
No cross-observation deduplication or persistent monitoring is established.

Exit 0 means every stock has a factual MATCH/NO_MATCH verdict; exit 1 means at
least one UNKNOWN; exit 2 is malformed input or terminal failure, with no partial
JSON. Rows preserve requested order. Joint comparability requires common session,
basis, schedule and source profile, and does not imply common acquisition time.

The external AI may cite and explain admitted facts, state its interpretation
separately, and identify absent evidence. It cannot calculate from raw prices,
invent context, infer eligibility, or translate a synthetic demonstration/test
pass into a current-market or effectiveness claim. Raw bars, numerical prices,
provider bodies, private paths and exception text are excluded from this output.

For an offline demonstration with fixed synthetic evidence, use the existing
project environment:

```sh
.venv/bin/python examples/causal_setup_screen_demo.py --scenario positive
.venv/bin/python examples/causal_setup_screen_demo.py --scenario negative
.venv/bin/python examples/causal_setup_screen_demo.py --scenario insufficient
```

These exercise the actual command with synthetic source adapters and a fixed
August 26 clock. They prohibit network access and hidden-directory creation.
Their outputs are contract demonstrations, not current market observations.
