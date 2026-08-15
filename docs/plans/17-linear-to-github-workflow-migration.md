# Plan 17: Linear-to-GitHub development-workflow migration

Status: **PLANNED — OWNER APPROVED; EXECUTION BLOCKED UNTIL SPRINT 9 IS COMPLETE**

Date planned: 2026-08-15

Owner: Krunal Dodiya

Execution start condition: Sprint 9 is merged, its hosted checks pass, its Linear records are terminally reconciled, and its sprint closeout is committed to `main`.

## 1. Plain-English purpose

Move active development planning from Linear into GitHub so that work items, code, pull requests, review, CI, GitGuardian, merge evidence, and completion state live in one operational system.

This plan is durable planning evidence only. Writing, reviewing, committing, or publishing this document does **not** create a GitHub Project, migrate an issue, change Linear, alter CI, start Sprint 10, or authorize any migration execution.

After cutover:

- GitHub Issues own active goals, stories, tasks, defects, acceptance criteria, hierarchy, and dependencies.
- One GitHub Project owns active status, sprint, priority, estimate, and risk views.
- Pull requests link to Issues and close them only after merge to the default branch.
- GitHub Actions and GitGuardian remain the delivery checks.
- Linear becomes historical source material only; it is no longer updated or consulted for current status.
- Existing `ARK-*` identifiers remain visible as historical provenance and migration cross-references.

## 2. Decision and expected value

**Decision:** adopt a GitHub-only active development workflow after Sprint 9.

Expected value:

- Remove duplicate GitHub/Linear status updates and closeout reconciliation.
- Bind issue, branch, commit, pull request, exact reviewed revision, hosted checks, merge, and closure in one traceable chain.
- Reduce contradictory states such as a merged pull request with an unfinished tracker issue.
- Give coding agents one issue and delivery API instead of two independent systems.
- Retain historical Linear evidence without making it an active second source of truth.

The expected improvement is workflow speed and evidence consistency, not runtime or coding speed. The migration itself temporarily adds work; the benefit begins after cutover.

## 3. Scope

### 3.1 In scope

1. Freeze and export the complete Linear inventory after Sprint 9 closeout.
2. Create exactly one GitHub Project for this repository.
3. Define the minimum GitHub labels, fields, iteration, views, and built-in workflows.
4. Migrate all still-actionable Linear work as individual GitHub Issues.
5. Preserve completed Linear work through closed sprint archive Issues, one closed non-sprint archive Issue, a complete cross-reference index, and a restricted canonical export.
6. Preserve material comments, hierarchy, dependency, relation, timestamp, and evidence links.
7. Add stable GitHub issue and pull-request templates.
8. Update project workflow documentation so GitHub is the only active work tracker.
9. Add a narrow provider-neutral tracker-cutover rule to the global handbook; do not make the global handbook GitHub-specific.
10. Verify counts, identities, mappings, permissions, automation, closing behavior, exports, and rollback before deactivating Linear.
11. Run one controlled GitHub-only delivery exercise before declaring the migration complete.

### 3.2 Out of scope

- Sprint 9 implementation, probe, decision, review, publication, or closeout.
- Sprint 10 or any market-data acquisition.
- Moving the repository from the personal account to a GitHub organization.
- Replacing GitHub Actions, GitGuardian, Git, pull requests, or branch protection.
- Rewriting old sprint records as if GitHub had historically owned them.
- Recreating all completed Linear milestones as active GitHub milestones.
- Introducing a permanent Linear/GitHub synchronization service.
- Adding a custom GitHub App, PAT-backed Action, webhook, bot, or GraphQL workflow unless the built-in features fail a documented requirement.
- Changing market logic, data contracts, source authority, licensing, trading scope, or runtime behavior.

## 4. Non-negotiable invariants

1. **No execution before Sprint 9 completion.** Planning may be published; migration writes may not begin.
2. **One active source of truth.** During preparation Linear remains authoritative. At the recorded cutover instant GitHub becomes authoritative. Permanent dual tracking is forbidden.
3. **Historical truth is not rewritten.** Old `ARK-*` identifiers, Linear URLs, old status snapshots, pull requests, commit SHAs, CI runs, decisions, and timestamps remain evidence of what happened then.
4. **Imported records are honest.** A GitHub issue created during migration must not pretend its GitHub creation timestamp or author is the original Linear timestamp or author.
5. **No silent loss.** Every Linear issue in the sealed export maps to an active GitHub Issue or a named archive anchor.
6. **No guessed relationships.** Parent, blocking, related, duplicate, and carryover relationships are copied only from retained evidence.
7. **No secret expansion.** Existing `.github/workflows/ci.yml` keeps `contents: read`; Project credentials are not added to CI.
8. **No active Project drafts.** Active requirements are repository Issues so they can link to code, PRs, and repository history.
9. **Merge owns completion.** Project status must never close an issue merely because a card moved to Done. A merged default-branch PR using a closing keyword, or an explicit reviewed no-code close decision, owns closure.
10. **Rollback stays possible until acceptance.** Linear access and the pre-cutover snapshot remain available until every verification gate passes.

## 5. Current-state evidence snapshot

The discovery snapshot was taken read-only on 2026-08-15. It must be refreshed immediately before migration; these counts are planning inputs, not fixed execution assertions.

### 5.1 Linear inventory

- Total issues: **185**.
- State distribution: 160 Done, 13 Canceled, 3 Duplicate, 5 Backlog, 2 Todo, 2 In Progress.
- Archived issues: 0.
- Sprint 9: ARK-183 and ARK-184 In Progress; ARK-185 Todo.
- Unique sprint-associated issues: 137.
- Terminal non-sprint issues: 42 after the projected Sprint 9 close.
- Projected actionable issues after Sprint 9: 6, if no other state changes.
- Parent edges: 112; maximum observed hierarchy depth: 3.
- Parent edges crossing proposed archive buckets: 46.
- Linear cycles: 0; sprint membership is label-based.
- Linear label groups cannot be reproduced directly by GitHub flat labels.
- Comments, native relations, attachments, and state histories require per-record extraction; the bulk issue listing is not a complete export.

### 5.2 Projected individually migrated open issues

Refresh this list at cutover. Under the current snapshot, migrate these records individually:

| Linear ID | Current state | Purpose | Required preservation |
|---|---|---|---|
| ARK-154 | Todo | Reconcile approved hierarchical universe and reference governance | Two comments, nine historical related links, latest accepted direction |
| ARK-153 | Backlog | Sanitize threshold-decision CLI argument failures | Three historical related links |
| ARK-152 | Backlog | Fail closed on unsupported canonical catalog WAL state | One historical related link |
| ARK-122 | Backlog | Make Goal subagent coordination event-driven | Seven evidence/circuit-breaker comments |
| ARK-64 | Backlog | Keep third-party market-book PDFs local and untracked | One historical related link |
| ARK-39 | Backlog | Publish reusable market-data package with PyPI Trusted Publishing | Historical parent ARK-10 |

There are currently no live-to-live dependency edges among these six. Their relations point to terminal historical records and therefore become archive links, not invented active dependencies.

### 5.3 Project repository coupling

Active Linear coupling is documentation and status governance, not runtime code. No Linear SDK, token, script, webhook, workflow, or source integration was found.

Primary active migration surfaces after Sprint 9 merges:

- `docs/sprints/README.md`: active source-of-truth rule.
- `docs/roadmap.md`: active planning and closeout pointer.
- `upcoming_sprints_overview.md`: active Linear query/label/reconciliation language.
- `docs/plans/16-market-regime-layer-b-acquisition-decision.md`: Sprint 9 tracker hierarchy and closeout requirement.
- `docs/sprints/sprint-9.md`: final Sprint 9 tracker truth and closeout.

Historical records that must not be rewritten include:

- Completed sprint files and old `ARK-*` mappings.
- `docs/sprints/sprint-2-time-accountability-ledger.json`.
- Tests asserting frozen historical Linear evidence.
- Plans 14 and 15 historical ARK/PR/SHA evidence.
- Sprint 8 and Sprint 9 final historical status snapshots.

### 5.4 Global handbook coupling

The global software-engineering handbook is already provider-neutral. It contains no Linear, Jira, GitLab, Azure DevOps, or GitHub work-tracker mandate. GitHub URLs there are source-provenance links, not tracker policy.

Therefore the handbook migration is deliberately narrow:

- Do not replace “Linear” with “GitHub”; no such active mandate exists.
- Preserve the handbook’s project/provider/tool-neutral scope.
- Add a provider-neutral cutover invariant: the project adapter must name the authoritative tracker before, during, and after migration; coexistence must be bounded; superseded identifiers and history must remain traceable.
- Put the GitHub-specific mapping in this repository’s project adapter/workflow documentation, not in global normative chapters.

## 6. Target GitHub workflow

### 6.1 Ownership

Use exactly one **user-owned GitHub Project** linked to `krunaldodiya/SwingTradingAIAssistant`.

Proposed name: `SwingTradingAIAssistant Delivery`.
Access default: the Project is private, Krunal Dodiya is its sole Admin, and no collaborator receives Project access during migration. Any later collaborator requires an owner-approved row naming the person, business need, Project role (`Read`, `Write`, or `Admin`), separate repository role, start, expiry/review date, and revocation owner. Project access never substitutes for repository access.

This decision assumes the observed personal-account topology. Phase 0 must stop and amend/re-review this plan if live preflight finds organization ownership; it must not improvise an organization Project, Issue Types, or a different access model. Do not transfer the repository to an organization merely to obtain organization-only Issue Types. Under the approved personal-account topology, use labels for work type.

### 6.2 Active records

- Repository GitHub Issues are the work records.
- One coherent goal Issue may own story/task sub-issues.
- Native sub-issues preserve hierarchy.
- Native issue dependencies preserve blocking.
- Pull requests link to Issues using `Closes #NUMBER` in the PR body.
- PRs are not added as duplicate Project items; the Project displays linked pull requests on the Issue.
- Draft Project items are never authoritative requirements.

### 6.3 Minimum labels

Create only labels needed by the active workflow:

- `kind:goal`
- `kind:story`
- `kind:task`
- `kind:defect`
- `tdd`
- Existing domain/risk labels only where an active work item needs them
- `imported-from-linear` for migrated individual Issues and archive Issues

Historical Linear work-type labels remain inside archive metadata. Do not recreate unused or purely historical label groups as active GitHub taxonomy.

### 6.4 Minimum Project fields

| Field | Type | Values/meaning |
|---|---|---|
| Status | Built in | Todo, In Progress, Done |
| Priority | Single select | Urgent, High, Medium, Low; unset means no priority |
| Estimate | Number | Planning-size units only; never labor hours |
| Sprint | Iteration | Seven-day delivery windows; breaks are explicit |
| Risk | Single select | Low, Moderate, High, Critical; migrated items remain unset until an owner-approved item-level assessment |
| Legacy Linear ID | Text | `ARK-*` for imported records; blank for new GitHub-native work |
| Parent issue | Built in | Native hierarchy; do not duplicate |
| Sub-issue progress | Built in | Derived progress; do not duplicate |
| Linked pull requests | Built in | Delivery link; do not duplicate |

Blocked work is represented by native dependencies, not another Status value.

### 6.5 Minimum views

1. **Backlog** — table of open Issues; group by Sprint; sort by Priority; show Status, Priority, Estimate, Risk, Parent issue, Legacy Linear ID.
2. **Current Sprint** — board of open Issues in `@current`; columns by Status; show Priority, Estimate, Risk, Parent issue.
3. **Hierarchy** — table grouped by Parent issue; show Sub-issue progress and Linked pull requests.

Do not create a roadmap view until a demonstrated planning need exists.

### 6.6 Minimum built-in automation

- Auto-add Issues from this repository to the Project.
- Closed Issue → Status Done.
- Default-branch PR with `Closes #NUMBER` closes the linked Issue; the closed-Issue workflow then sets that Issue item’s Status to Done.
- Do **not** enable Status Done → close Issue.
- Explicitly backfill migrated Issues because auto-add does not backfill existing matches.

Use built-in workflows first. Do not add Project credentials or custom Actions in the initial migration.

### 6.7 Stable repository templates

Prefer stable Markdown templates over preview-only Issue Forms for the first cutover:

- `.github/ISSUE_TEMPLATE/work-item.md`
- `.github/ISSUE_TEMPLATE/defect.md`
- `.github/ISSUE_TEMPLATE/config.yml`
- `.github/pull_request_template.md`

Work-item template sections:

- Goal/outcome
- Scope and non-goals
- Observable acceptance
- Dependencies/parent
- Risk and stop conditions
- Evidence required for closure

Defect template sections:

- Observed behavior
- Expected behavior
- Reproduction and evidence
- Root-cause hypothesis, clearly marked until proven
- Regression acceptance

PR template sections:

- `Closes #...`
- Observable change
- Exact verification evidence
- Risk and limitations
- Exact candidate revision/review evidence where required

## 7. Linear-to-GitHub mapping contract

| Linear concept | GitHub destination | Rule |
|---|---|---|
| Issue identifier | Legacy Linear ID field and body link | Never replace or drop `ARK-*` |
| Title | Issue title | Preserve meaning; correct only demonstrable truncation/encoding defects |
| Description | Issue body | Prefix imported metadata; preserve acceptance and current truth |
| Todo/Backlog | Open Issue, Status Todo | Backlog has no assigned Sprint |
| In Progress | Open Issue, Status In Progress | Must reflect fresh cutover snapshot |
| Done | Closed archive record | Do not create as a falsely historical individual live Issue under the recommended archive model |
| Canceled/Duplicate | Archive record with exact terminal reason | Never map to Done |
| Parent | Native parent/sub-issue or archive anchor | No inferred parents |
| Blocks/blocked by | Native dependency when both sides are active; otherwise typed archive link | No invented live dependency |
| Related | Body/reference link | Preserve type and target |
| Sprint label | Archive bucket for history; Iteration for future work | Do not continue sprint labels as active timebox truth |
| Work type | `kind:*` label for active work; original value in archive | GitHub Issue Types are not assumed |
| Priority | Project Priority field | Preserve explicit “no priority” as unset |
| Estimate | Project Estimate field | Planning size, never elapsed hours |
| Risk | Project Risk field | Leave migrated work unset unless the owner approves an item-level assessment in the dry-run manifest; never derive risk from priority or labels |
| Project/milestone | Imported metadata and archive link | Do not create 15 historical live milestones |
| Comment | Authorship/timestamp-prefixed migrated comment or archive evidence | State clearly that the GitHub author/time is migration metadata |
| Attachment/document | Restricted exported artifact plus issue/archive link | Verify checksum and access before publication |
| Original timestamps | Imported metadata block | GitHub timestamps are not backdated |
| PR/SHA/CI evidence | Existing GitHub URLs and exact identities | Preserve without rewriting |

## 8. Historical preservation design

### 8.1 Recommended archive shape

After Sprint 9 closes and the final snapshot is sealed:

- Create one closed GitHub archive Issue for each Sprint 0 through Sprint 9.
- Canonically assign each multi-sprint Linear record to its latest sprint archive and cross-reference every earlier timebox.
- Preserve Sprint 2’s historical denominator/carryover truth even when canonical records live in Sprint 3’s archive.
- Create one closed `Non-sprint Linear history` archive Issue for terminal records with no sprint.
- Create one master migration index mapping every Linear ID to either an individual GitHub Issue URL or an archive Issue anchor.

Projected canonical sprint archive counts, subject to the fresh cutover snapshot:

| Archive | Records |
|---|---:|
| Sprint 0 | 14 |
| Sprint 1 | 24 |
| Sprint 2 | 24 |
| Sprint 3 | 47 |
| Sprint 4 | 4 |
| Sprint 5 | 4 |
| Sprint 6 | 4 |
| Sprint 7 | 6 |
| Sprint 8 | 7 |
| Sprint 9 | 3 |
| Non-sprint terminal history | 42 |

Expected total after Sprint 9 and with the current six open records unchanged: 179 archived records + 6 individual open Issues = 185.

### 8.2 Canonical export

Before any write, produce a bounded, canonical export containing:

- Every issue field and original URL.
- Complete state history where available.
- Parent, blocks, blocked-by, related, duplicate, and carryover relationships.
- Comments with original author identity and timestamps.
- Attachment/document metadata, retained identities, and bounded content bytes where access and permitted retention allow.
- Sprint, project, milestone, priority, estimate, labels, and dates.
- A deterministic Linear-ID ordering.
- A manifest with record counts, byte count, SHA-256, export time, tool/code revision, and pagination receipts.

The raw export may contain sensitive or personal information. Before any hosted write, approve a field-level publication matrix covering issue fields, names/emails, comments, private URLs, documents, attachment metadata, and attachment bytes; each class is `PUBLIC_OR_REPOSITORY_VISIBLE`, `REDACTED`, `OMITTED_WITH_REASON`, or `RESTRICTED_ARCHIVE_ONLY`. Do not commit or attach raw content until repository visibility, collaborator access, licensing/retention rights, and that matrix are verified. Publish only the approved sanitized index to Issues. Store the raw canonical export and exportable attachment/document bytes as a restricted GitHub-hosted asset only if its access boundary and download verification are proven; otherwise retain them in an owner-approved encrypted archive and record identity/location without exposing contents. If material evidence cannot be exported or safely retained and Linear access cannot remain available under an approved retention exception, the migration is `BLOCKED`, not partially complete.

The active workflow is still GitHub-only even if confidential historical evidence must remain in a restricted archive; that archive does not own current work state.

## 9. Detailed execution plan

Every phase is independently reviewable. Do not advance when a gate fails.

### Phase 0 — activation gate and live preflight

**Goal:** prove that migration may begin and replace planning assumptions with live facts.

Tasks:

1. Confirm Sprint 9 PR is merged to `main` and hosted CI/GitGuardian passed on the merged candidate.
2. Confirm ARK-183, ARK-184, and ARK-185 are terminally reconciled and Sprint 9 closeout is committed.
3. Confirm the owner has resumed work and explicitly authorized migration execution.
4. Confirm Sprint 10 has not started and no other active sprint is open.
5. Query live GitHub repository ownership, visibility, Issues enablement, collaborator roles, branch/ruleset settings, labels, milestones, Projects, and user Project permissions. Stop for plan amendment and re-review if ownership is not the approved personal-account topology.
6. Query a fresh complete Linear inventory, including all issue details, state histories, comments, documents, attachments, and relations.
7. Compare fresh counts with this planning snapshot; update the execution manifest rather than forcing old counts.
8. Approve the field-level publication matrix and the storage/retention location for raw Linear exports and attachment/document bytes.
9. Record an operation-by-operation access matrix: Linear export/read, Linear final freeze marker, GitHub Issue/archive writes, Project configuration, repository template PR, Project/API snapshot, and credential revocation. For each, name the operator, exact interface, minimum permission/token scope, secret location, expiry/revocation action, and proof. Separately approve the destination Project visibility and every Project `Read`/`Write`/`Admin` principal; default to private, owner-only Admin. CI must have no Project or Linear credential.
10. Record the exact cutover authority, operator, expected migration window, rollback owner, and stop conditions.

Verification:

- Sprint 9 merge SHA and check URLs exist.
- No open Sprint 9 Linear issue remains.
- Fresh Linear pagination is complete and count-reconciled.
- GitHub account topology and permissions are observed, not inferred.
- No GitHub writes have occurred.

Stop conditions:

- Sprint 9 is incomplete.
- A second active sprint exists.
- Linear export is incomplete.
- GitHub Issue/Project permissions are insufficient.
- Repository visibility makes the proposed historical export unsafe.
- Live repository ownership differs from the approved personal-account topology.
- The field-level publication matrix or attachment/document retention decision is incomplete.
- Any required operation lacks a proven least-privilege credential and revocation path.
- The owner has not resumed/authorized execution.

### Phase 1 — freeze contracts and write RED migration tests

**Goal:** define a deterministic, restart-safe migration before making hosted writes.

Tasks:

1. Write a migration specification with exact source schema, destination schema, mapping, pagination, size bounds, retry policy, deterministic source markers, receipts, redaction, failure states, ambiguous-write adjudication, and rollback rules. GitHub Issue creation has no assumed provider idempotency guarantee.
2. Write RED tests for:
   - Complete pagination and duplicate rejection.
   - Canonical ordering and export identity.
   - Exact state/type/priority/estimate/sprint mapping.
   - Risk remaining unset unless the reviewed dry-run manifest contains an owner-approved item-level assessment.
   - Parent and dependency graphs, including cross-archive edges.
   - Comment author/time preservation labels.
   - Active-vs-archive classification.
   - Every Linear ID resolving exactly once.
   - Dry-run versus apply separation.
   - Rerun/resume without duplicate GitHub Issues by reconciling deterministic source markers and retained response receipts.
   - Ambiguous timeout/connection outcomes stopping for read-after-write reconciliation rather than retrying creation.
   - Partial failure and resume from retained receipts.
   - Field-level redaction plus confidential attachment/document retention.
   - Count and checksum reconciliation.
3. Keep migration code outside the trading runtime package.
4. Do not add a reusable Linear runtime dependency or background synchronization service.

Verification:

- Tests fail only because migration implementation is absent.
- No hosted system was mutated.
- Test fixtures are sanitized and contain no credentials or unnecessary personal data.

Anti-pattern guards:

- No caller-authored “success” receipt.
- No title-only identity matching.
- No best-effort skip of malformed records.
- No unbounded pagination or comment/attachment reads.
- No “continue on error” final success.

### Phase 2 — implement read-only export, classifier, and dry run

**Goal:** produce a complete proposed mapping without creating GitHub records.

Tasks:

1. Implement a one-off deterministic migration tool using the smallest supported interfaces.
2. Fetch Linear pages and per-record history/comments/relations with explicit bounds and retained receipts.
3. Produce the canonical raw export, sanitized index, migration manifest, and proposed destination records.
4. Classify records from fresh state:
   - Active records → individual Issues.
   - Terminal sprint records → sprint archive Issues.
   - Terminal non-sprint records → non-sprint archive Issue.
5. Resolve all 112-or-current parent edges and every native relation through the master index.
6. Produce a no-write dry-run report containing destination titles, labels, bodies, fields, hierarchy, dependencies, comments, archive anchors, and count checks.
7. Give every proposed GitHub record a unique, machine-readable source marker derived from its canonical source key (for example `linear-import:ARK-154` or `linear-archive:sprint-3`). Define a pre-create exact-marker search, a post-create response receipt, and a read-after-write reconciliation path. A timeout or ambiguous response must stop; it must never blindly retry a create.
8. Produce the approved item-level Risk decisions; absent an explicit owner decision, the destination Risk value is unset.
9. Reject unknown states, duplicate IDs, missing parents, unresolved relation targets, identity mismatches, unsafe content, or ambiguous prior writes.

Verification:

- Source total equals active individual total plus archived-record total.
- Every Linear ID maps exactly once.
- Every relation endpoint resolves.
- All bytes and manifests reproduce on a second isolated run against the sealed source export.
- Independent review approves the dry-run report.

### Phase 3 — configure the minimum GitHub destination

**Goal:** create the empty GitHub workflow structure without changing source-of-truth authority.

Tasks:

1. Reconfirm the approved personal-account topology; otherwise stop for plan amendment and review.
2. Create the required `kind:*`, `tdd`, and `imported-from-linear` labels.
3. Create the single private user-owned Project with Krunal Dodiya as sole Admin and no other Project principals.
4. If the approved access matrix contains a collaborator, grant only its exact Project role and confirm its separate repository role; otherwise keep the collaborator list empty.
5. Add only the fields and values specified in section 6.4.
6. Configure the Backlog, Current Sprint, and Hierarchy views.
7. Configure the minimum built-in workflows from section 6.6.
8. Add stable Markdown Issue templates, template configuration, and PR template through a reviewed repository PR.
9. Document the Project owner, visibility, every Read/Write/Admin principal, Project URL/number, field IDs/options, iteration schedule, view filters, workflow settings, access matrix, and exact rollback operations in the project adapter.
10. Export an empty/configured Project snapshot before importing work.

Verification:

- Project is linked only to the intended repository.
- Project visibility is private; the observed Project collaborator/role list equals the approved matrix exactly.
- Owner access succeeds. An unauthenticated API/web request and, when an independent test principal is available, that unapproved principal cannot read the private Project. Repository-private item visibility is separately verified because Project access does not grant repository access.
- Ordinary Issues auto-add without credentials.
- CI permissions remain unchanged.
- Moving a card to Done does not close an Issue.
- Repository templates render expected headings and labels.
- No Linear state has changed.

### Phase 4 — migrate historical archives first

**Goal:** establish complete historical anchors before importing active work.

Tasks:

1. For each archive, perform exact-marker lookup before creation. If one matching record exists, verify it against the proposed bytes and resume; if none exists, create once and retain the response; if multiple or ambiguous results exist, stop.
2. Create the Sprint 0–9 archive Issues from the sealed proposed records.
3. Create the non-sprint terminal archive Issue.
4. Create the master migration index with stable anchors.
5. Close archive Issues using the appropriate “not planned”/completed representation documented in their bodies; do not imply GitHub performed the historical work.
6. Preserve original Linear states distinctly: Done, Canceled, and Duplicate must not collapse into one meaning.
7. Preserve cross-sprint carryovers and cross-archive hierarchy/relations through explicit links.
8. Attach or link only the reviewed sanitized archive evidence.
9. Record created Issue numbers, source markers, and response identities in the migration receipt.

Verification:

- Archive record counts reconcile to the manifest.
- Every archived `ARK-*` has a stable GitHub anchor.
- Sample all small archives; statistically and risk-select samples from large archives; fully verify records with dense comments/relations such as ARK-92.
- No archive Issue appears as active backlog work.
- Imported GitHub timestamps/authorship are clearly labeled as migration metadata.

### Phase 5 — migrate active work and relationships

**Goal:** create complete GitHub-native working records while Linear is still temporarily authoritative.

Tasks:

1. For each active source record, perform the same exact-marker lookup and ambiguous-write adjudication used for archives. Creation is single-attempt; resume uses retained receipts plus read-after-write verification, never blind retry.
2. Create each fresh actionable Linear record as an individual GitHub Issue with:
   - Original Linear ID and URL.
   - Original created/updated/start/due timestamps.
   - Current accepted description and acceptance criteria.
   - Priority, estimate, labels, assignee, and Project fields.
   - Risk unset unless the reviewed dry-run manifest contains an owner-approved item-level assessment.
   - Historical comment and archive links.
3. Add every new Issue explicitly to the Project because auto-add does not backfill.
4. Create native parent/sub-issue links where both records are active.
5. Create native blocking links where both records are active.
6. Represent active-to-archive relations as typed links, not live dependencies.
7. Recreate comments only when they contain material decision/evidence; include the original author/time header and retain all comments in the canonical export.
8. Record deterministic source-ID/destination-number mappings, source markers, and API receipts.

Verification:

- Every active Linear record has exactly one open GitHub Issue.
- Titles, current truth, acceptance, status, priority, estimate, sprint, labels, and assignee match the approved mapping; Risk is either the explicit owner-approved value in the manifest or unset.
- Every material comment and relation is preserved.
- A full resume/rerun reconciles source markers and receipts without creating a duplicate Issue.
- Linear remains unchanged during this shadow verification period.

### Phase 6 — independent full reconciliation and decision gate

**Goal:** prove GitHub is a complete replacement before changing authority.

Required independent reviews:

1. **Completeness review:** counts, every ID, comments, attachments, relations, archives, active records.
2. **Workflow review:** Issue hierarchy, dependencies, Project fields/views/iterations, PR linking, closure semantics.
3. **Security/privacy review:** credentials, export access, personal data, attachment visibility, permissions, Action scopes.
4. **Historical-integrity review:** no rewritten dates/authors/states, preserved ARK/PR/SHA/CI evidence.
5. **Anti-pattern review:** no dual-tracker automation, no CI token expansion, no draft requirements, no invented dependencies, no false completion.

Decision outcomes:

- `APPROVED_TO_CUT_OVER`: all gates pass on one exact migration candidate and snapshot identity.
- `BLOCKED`: one or more named discrepancies remain; Linear stays authoritative and no project documentation is switched.

Any repair changes the candidate identity and requires re-review.

### Phase 7 — prepare project authority documentation

**Goal:** produce and approve the project documentation change without switching authority or merging it.

Tasks:

1. Prepare active project document changes:
   - `docs/sprints/README.md`
   - `docs/development-workflow.md`
   - `docs/engineering-standards.md` only where tracker evidence interacts with an existing standard
   - `docs/roadmap.md`
   - `upcoming_sprints_overview.md` or replace its active pointer with a current GitHub-backed record
   - Active templates and autonomous-orchestration guidance
2. Keep `AGENTS.md` product/research rules provider-neutral unless a concise project-adapter pointer is required.
3. Freeze completed Sprint 0–9 documents as historical evidence; add successor/migration links without replacing their old `ARK-*` facts.
4. Prepare text that, only when merged at Phase 9’s cutover instant, establishes:
   - GitHub Issues own work records and acceptance.
   - The named GitHub Project owns status, iteration, priority, estimate, and risk views.
   - Pull requests and hosted checks own delivery evidence.
   - Repository sprint records own concise retained closeout evidence.
5. Remove active Linear reconciliation steps and direct-Linear requirements from current/future workflow instructions.
6. Do not modify frozen tests whose purpose is to prove historical Linear evidence.
7. Open the authority-switch PR, run normal CI/GitGuardian, obtain exact-revision approval, and leave it unmerged until Phase 9.

Verification:

- The approved PR would name only GitHub as active tracker authority after merge.
- Historical searches still find preserved `ARK-*` evidence.
- No active instruction in the candidate requires updating both trackers.
- Documentation assertions distinguish current policy from historical records.
- Linear remains authoritative because the PR has not merged.

### Phase 8 — update the global handbook narrowly

**Goal:** strengthen provider-neutral migration governance without turning the global handbook into a GitHub manual.

Tasks:

1. Add provider-neutral tracker-migration rules to the most relevant lifecycle/agile chapter:
   - The project adapter names unambiguous authoritative ownership for each active record/state throughout migration.
   - Temporary coexistence has an owner, start, end, rollback condition, and removal criteria.
   - The project adapter defines its cutover model; this repository uses one recorded instant, but the global handbook does not require that model universally.
   - Superseded identifiers/history remain linked and immutable.
   - Completion requires count/relation/evidence reconciliation.
2. Update the handbook index/project-adapter hook if necessary.
3. Keep GitHub mapping and exact Project configuration in the repository, not the global handbook.
4. Preserve GitHub-hosted OWASP/reference links and governance backup instructions; they are not tracker coupling.
5. Publish the handbook change through its own exact-revision review and controlled release process.

Verification:

- Exact search finds no named-tracker mandate in normative global handbook text.
- Provider-neutrality and local-over-global precedence remain intact.
- Live managed skill and enforcement rule still resolve to the reviewed handbook assets.

### Phase 9 — freeze Linear, merge authority, and test one real workflow

**Goal:** perform one controlled authority switch and prove the GitHub-only lifecycle end to end.

Tasks:

1. Reconfirm `APPROVED_TO_CUT_OVER`, the exact source/mapping identities, the still-approved authority-switch PR revision, and the rollback operator.
2. Enter a bounded no-write window: disable/revoke Linear mutation automation and operator credentials while retaining read-only access. Linear remains the authoritative frozen snapshot until the authority-switch PR merges.
3. Re-read Linear and GitHub records; abort and restore Linear mutation authority if either differs from the approved candidate.
4. Merge the already approved project authority PR. Its GitHub merge timestamp is this project’s single cutover instant; from that instant GitHub is authoritative.
5. Record the cutover timestamp, source export SHA-256, mapping manifest SHA-256, GitHub Project identity, migration receipt identity, reviewer decision, and rollback deadline in the GitHub migration record.
6. Add a final Linear historical marker only if it can be done under an explicitly retained one-shot credential and cannot alter work state: “Active tracking migrated to GitHub at [instant]; this workspace is historical.” Revoke that credential immediately. Do not rewrite individual records.
7. Create one small non-market test Issue using the new template.
8. Add it through the built-in Project workflow.
9. Set hierarchy/priority/estimate/risk/Sprint.
10. Create a branch and PR with `Closes #NUMBER`.
11. Run normal review, CI, GitGuardian, and merge.
12. Confirm the default-branch merge closes the Issue and the closed-Issue workflow sets Project Status to Done.
13. Confirm no Linear work record changed after the cutover snapshot.
14. Export Project TSV and paginated API snapshot; reconcile against the Project.

Verification:

- One and only one authority-switch instant is recorded.
- One end-to-end Issue→PR→checks→merge→Issue closure→Project Done chain succeeds.
- GitHub is the only mutated work tracker after cutover.
- The Project, Issue, PR, checks, and merge identities agree.
- Backup/export counts reconcile.

### Phase 10 — close migration and remove temporary machinery

**Goal:** end coexistence and leave a maintainable steady state.

Tasks:

1. Resolve every discrepancy or roll back before the rollback deadline.
2. Remove temporary migration credentials and local secret material.
3. Remove or archive one-off migration code if it has no justified operational reuse; retain manifests, sanitized mappings, receipts, tests that protect current workflow, and exact review evidence.
4. Retain the canonical confidential export only under its approved access/retention policy.
5. Mark Linear historical/read-only; cancel the subscription only after owner confirms export accessibility and rollback is no longer required.
6. Record final counts, Project identity, migration PR/merge SHA, hosted checks, security review, cutover instant, and Linear freeze evidence.
7. Create future development work only in GitHub.
8. Reassess workflow speed and failure rate after two GitHub-only sprints; do not add automation without measured need.

Definition of Done:

- Every source Linear ID resolves through the master index.
- All active work exists only as GitHub Issues.
- Historical work is available through GitHub archive anchors and retained export evidence.
- Project fields/views/workflows match the recorded configuration.
- Active project docs and agent workflow are GitHub-only.
- Global handbook remains provider-neutral with explicit per-record/state authority and bounded-coexistence safety.
- CI permissions are unchanged.
- One real GitHub-only delivery lifecycle passed.
- No unresolved dual-tracking window remains.

## 10. Rollback plan

Rollback is allowed only before migration closeout.

Triggers:

- Missing or duplicated source records.
- Broken hierarchy/dependency mappings.
- Unsafe exposure of comments, attachments, or personal data.
- Incorrect Issue closure or Project automation.
- Insufficient permissions or inaccessible Project state.
- Unreconciled count, checksum, or identity mismatch.
- Documentation switched before hosted records are complete.

Procedure:

1. Stop all GitHub migration writes and revoke migration write credentials.
2. Preserve failed-run receipts and exact created Issue/Project identifiers.
3. Disable Project auto-add/status workflows; remove Project repository links and collaborator write access; archive and clearly quarantine the Project and imported records. Delete only when security requires controlled deletion and retained evidence proves what was removed.
4. Revert the migration-only template/configuration PR and, if it merged, the authority-switch documentation PR.
5. Mark created GitHub records as failed migration artifacts without pretending they are historical work.
6. Restore Linear mutation authority from the recorded pre-cutover access matrix only if the authority switch occurred or the no-write window had begun.
7. Reconcile any irreversible public disclosure separately; rollback cannot make exposed data secret again.
8. Repair from the sealed source export and resume through deterministic markers/receipts, or abandon the migration with an explicit owner decision.
9. Re-review the new exact candidate before another cutover attempt.

## 11. Security and privacy controls

- Never place Linear tokens, GitHub tokens, credentials, or raw API responses in repository files, issue bodies, logs, or comments.
- Use the approved operation-by-operation access matrix with least-privilege, short-lived operator credentials and explicit expiry/revocation proof.
- Do not widen `.github/workflows/ci.yml` permissions; CI receives no Linear or Project credential.
- Prefer built-in Project workflows; no custom credential-bearing Action in the minimum design.
- Treat comments, attachments, documents, names, emails, and private URLs as potentially sensitive.
- Approve and enforce the field-level publication matrix before the first hosted write.
- Sanitize fixture/export examples.
- Verify repository and asset visibility before uploading historical exports.
- Fetch and hash permitted attachment/document bytes; metadata alone is not durable preservation. A material unexportable record blocks deactivation unless an approved retained-access exception exists.
- Hash every retained export and mapping manifest.
- Bound pagination, response size, comment count, attachment size, retry count, and execution time in the migration specification.
- Use deterministic source markers and retained response receipts; an ambiguous create outcome stops for read-after-write reconciliation and is never blindly retried.
- Fail closed on partial reads, unknown fields/states, missing parents, unresolved relations, unsafe publication classes, or identity mismatches.

## 12. Scalability and maintenance limits

The recommended design is comfortably within current documented GitHub limits:

- Sub-issues: up to 100 per parent and 8 nested levels; observed Linear depth is 3 and largest observed parent has 21 children.
- Project fields: up to 50; this design uses five custom fields plus built-ins.
- Project items: up to 50,000 active plus archived; current work inventory is 185.
- One built-in auto-add workflow fits the minimum GitHub plan.

Do not infer that these limits guarantee a full backup. GitHub Project TSV export covers the currently open view and is not a restore format. Maintain paginated API snapshots and count/identity verification.

## 13. Required evidence package

The final migration closeout must link:

- Sprint 9 merge and closeout evidence.
- Fresh Linear source inventory and canonical export identity.
- Migration mapping manifest identity.
- Dry-run report and independent approvals.
- GitHub Project URL/number, owner, fields/options/iterations/views/workflows.
- Master `ARK-*` → GitHub Issue/archive index.
- Created archive and active Issue URLs.
- Reconciliation report for counts, hierarchy, dependencies, comments, attachments, and relations.
- Security/privacy review.
- Project documentation PR, exact reviewed SHA, hosted CI/GitGuardian, and merge SHA.
- Global handbook PR/release evidence.
- Controlled GitHub-only workflow Issue/PR/check/merge evidence.
- Post-cutover Project TSV/API snapshot identities.
- Linear freeze/read-only evidence and final rollback disposition.

## 14. Official GitHub capability sources

- Issues: https://docs.github.com/en/issues/tracking-your-work-with-issues/learning-about-issues/about-issues
- Sub-issues: https://docs.github.com/en/issues/tracking-your-work-with-issues/using-issues/adding-sub-issues
- Sub-issues REST: https://docs.github.com/en/rest/issues/sub-issues
- Issue dependencies: https://docs.github.com/en/issues/tracking-your-work-with-issues/using-issues/creating-issue-dependencies
- Projects overview: https://docs.github.com/en/issues/planning-and-tracking-with-projects/learning-about-projects/about-projects
- Project fields: https://docs.github.com/en/issues/planning-and-tracking-with-projects/understanding-fields
- Iteration fields: https://docs.github.com/en/issues/planning-and-tracking-with-projects/understanding-fields/about-iteration-fields
- Built-in Project automation: https://docs.github.com/en/issues/planning-and-tracking-with-projects/automating-your-project/using-the-built-in-automations
- Project auto-add: https://docs.github.com/en/issues/planning-and-tracking-with-projects/automating-your-project/adding-items-automatically
- PR-to-Issue linking: https://docs.github.com/en/issues/tracking-your-work-with-issues/using-issues/linking-a-pull-request-to-an-issue
- Project API: https://docs.github.com/en/issues/planning-and-tracking-with-projects/automating-your-project/using-the-api-to-manage-projects
- GitHub CLI Project commands: https://cli.github.com/manual/gh_project
- Project export: https://docs.github.com/en/issues/planning-and-tracking-with-projects/managing-items-in-your-project/exporting-your-projects-data

## 15. Tomorrow’s starting point

Do not recreate this plan. Resume from this document after Sprint 9 completes.

The first executable action is **Phase 0 only**: verify Sprint 9 closeout and refresh the read-only Linear/GitHub snapshots. If any activation gate fails, stop without creating a Project or migrating an Issue.
