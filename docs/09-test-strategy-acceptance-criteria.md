# Test Strategy & Acceptance Criteria

**Architecture pivot (2026-08-15):** acceptance criteria below were written for separate domain agents; read "the agent"/"an agent" throughout as the one master agent. AC-9/AC-10's "which agent" framing is superseded by "which tool source contributed the grounding" — see `07-system-architecture.md`'s pivot note. The criteria themselves (grounding correctness, progress updates, credential handling) are unaffected.

## Test strategy

### Layers

| Layer | What's tested | Tooling |
|---|---|---|
| **MCP tool wrappers** (ChEMBL/Open Targets/PubMed configs, pipeline wrappers) | Each wrapper returns correctly-shaped data and fails gracefully (timeout, malformed response, auth failure) | Unit tests per wrapper, mocking the underlying API/service |
| **Grounding Layer** | Every `RESPONSE` has a `provenance_type`; `grounded` responses have ≥1 `GROUNDING_LINK`; `ungroundable` responses are never silently rendered as `grounded` | Unit tests against the Grounding Layer's own logic, independent of any real LLM call |
| **Message Router** | Correct `TASK` created from a Mattermost webhook payload; correct agent resolved from `@mention` | Unit tests with fixture webhook payloads |
| **Credential Vault** | Encryption/decryption round-trips correctly; a credential is never returned in plaintext via any read path except the one call site that injects it into a tool call | Unit tests + a deliberate "grep the logs for plaintext secrets" check in CI |
| **Orchestrator ↔ Mattermost integration** | A real message posted to a real (test) Mattermost instance triggers the full router → agent → response cycle | Integration tests against a docker-composed Mattermost test instance |
| **Orchestrator ↔ pipeline integration** | Triggering a pipeline run via the wrapper produces the same result as triggering it via the pipeline's own existing interface (regression, not new behavior) | Integration test comparing wrapper output to the pipeline's own known-good output for a fixed input |
| **End-to-end journeys** | The six journeys in `08-cross-feature-journeys.md`, run against a real (test) deployment | Manual QA pass at MVP; scripted E2E automation is a fast-follow, not MVP-blocking |

### What's explicitly *not* tested at MVP

- Load/scale testing (single-org MVP; premature per `01-project-goals.md` Non-Goals).
- The sandboxed tool-runner (doesn't exist yet — Section 7 Phase 2, deferred).
- Multi-tenant credential isolation under adversarial conditions (single-org MVP; real security testing is scoped to whenever multi-tenant hosting is actually built, per the research report's own Appendix caveat).

### Grounding correctness — the test that matters most

Because "never present an ungrounded claim as fact" is the platform's core promise (Section 11 of the research report), this gets a dedicated test category beyond the standard layers above: a fixture set of known agent responses (some correctly grounded, some deliberately missing sources) run through the Grounding Layer, asserting it correctly classifies each and blocks any `grounded`-labeled response that doesn't actually have a backing `TOOL_CALL`. This is treated as a release-blocking test category, not a nice-to-have.

---

## Acceptance criteria

Written Given/When/Then, numbered for cross-reference from `08-cross-feature-journeys.md`.

**AC-1** — Given a researcher DMs the Literature Agent a question, when the agent responds, then the response includes at least one grounding-block citation with a resolvable PMID or DOI. *(Journey 1)*

**AC-2** — Given an agent cannot find a grounded source for part of its answer, when it responds, then that part is explicitly labeled as ungrounded synthesis, not presented with the same visual/textual weight as a sourced claim. *(Journey 1, UX Behavior §2)*

**AC-3** — Given a researcher triggers a repurposing pipeline run via the Drug Discovery Agent, when the run takes longer than 30 seconds, then the agent posts at least one progress update before final completion. *(Journey 2, FR-7)*

**AC-4** — Given a researcher asks a follow-up question in an existing task thread, when the agent responds, then the new response is grounded independently (does not silently reuse stale grounding from the earlier response without re-verifying it still applies). *(Journey 1)*

**AC-5** — Given a repurposing pipeline run completes, when the agent posts the summary, then the grounding block cites the specific ChEMBL query ID(s), docking run ID, and any other pipeline-internal provenance data — not just "the pipeline says so." *(Journey 2)*

**AC-6** — Given a repurposing pipeline run fails partway through, when the agent reports back, then the failure message names the specific phase that failed and does not present any downstream (unrun) phase's output. *(Journey 2 failure branch)*

**AC-7** — Given an agent needs a BYO-credentialed tool the org hasn't configured, when it responds, then it names the specific missing credential, points to where to add it, and — if a lower-tier free alternative exists — offers to proceed with that instead, explicitly labeled as a fallback. *(Journey 3, Section 9's fallback-tier rule)*

**AC-8** — Given an Operator registers a new credential, when it's stored, then the plaintext value is never returned by any subsequent read (API response, log line, or chat message) except the single internal call site that injects it into an authenticated tool request. *(Journey 4)*

**AC-9** — Given a Clinical/Commercial-cluster agent response involves regulatory/pharmacovigilance-adjacent content, when it posts, then it carries the reserved "requires expert review" visual marker and explicit review-required language — and this marker is never used for any other message type. *(Journey 5, Gap 10)*

**AC-10** — Given a multi-agent flagship pipeline task where one contributing agent's leg fails, when the parent response posts, then it delivers the successful legs' results and explicitly names which leg is missing and why — never silently presents a partial result as complete. *(Journey 6, Flagship 5.3's partial-dossier requirement)*

**AC-11** — *(superseded 2026-08-15 — bulk join replaced by on-demand retrieval, see `10-build-plan.md` Phase 0)* Given a topic query triggers the Discovery & Acquisition flow, when the Sci-Hub-availability lookup step runs against `data/scihub.sql`, then it completes in roughly the measured single-pass cost (~50-60s) regardless of candidate-DOI-list size, and every full-text response discloses which acquisition tier it came from (OA / BYO-paywalled / Sci-Hub) — replaces the original bulk-coverage measurement, which is no longer a build task.

## Related documents

`08-cross-feature-journeys.md` · `06-data-model.md` · `10-build-plan.md`
