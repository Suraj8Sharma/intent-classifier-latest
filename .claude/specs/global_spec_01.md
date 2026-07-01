**Specification: Intent Classifier Engine**

myitihas Platform

**Version 2.1**

_Revised to define the phased build sequence, formalize the Supabase data model for interest profiling, and scope the Epistemological Validation Layer as a planned future phase._

## Changelog — v2.0 → v2.1

| Area | Change |
| --- | --- |
| Build Sequencing | New §4 defines a strict 3-phase build order (core pipeline → validation plumbing → real validation checks) with ownership and exit criteria per phase. |
| Data Model | New §9 formalizes the Supabase schema: user_interests, profiling_jobs, and the additive intent_label column on the existing story/chat table. |
| Validation Layer | New §14 scopes the Epistemological Validation Layer at a product/architecture level only. Detailed algorithm and model design deferred to a dedicated Validation Layer spec. |
| Open Items | Three new stakeholder items added re: phase ownership, validation model sourcing, and schema migration timing. |

# 1\. Problem Statement

The myitihas platform currently delivers a monolithic response experience. We are simplifying our intent routing to three core pipelines to improve classification confidence and reduce architectural complexity.

This revision additionally formalizes how the engine is built and rolled out in stages, and how it will eventually support response-quality validation without destabilizing the core chat experience while that layer is still being designed.

# 2\. Goals & Non-Goals

## 2.1 Goals

*   Ship a reliable, low-latency three-way intent routing and generation pipeline (factual / creative\_story / philosophical) as the foundation everything else depends on.
*   Support safe, race-condition-free personalization via async interest profiling, without ever leaking that profile back into the classification step.
*   Make the response schema and storage layer structurally ready to carry future response-validation data, so that layer can be integrated later without a breaking change.
*   Establish full observability (LangSmith) from day one so classification drift and pipeline failures are auditable in production, not just in benchmarks.

## 2.2 Non-Goals (for this document)

*   Detailed algorithm design, model selection, or threshold tuning for the Epistemological Validation Layer — that is intentionally deferred to a dedicated spec (see §14).
*   UI/UX design for surfacing validation scores to end users (Ishani's dashboard work) — tracked separately.
*   Multi-language classification support beyond the current benchmark dataset.

# 3\. Functional Requirements

*   **FR-01: Intent Routing —** The engine must classify every user query into exactly one of three categories: factual (RAG), creative\_story, or philosophical.
*   **FR-02: Isolated Classification —** Classification must be performed using the current user query in isolation. No previous session history, turn context, or the user's interest\_vector may be present in the classification prompt. This isolation is a hard architectural guarantee, not a default (see §6).
*   **FR-03: Async Batch Profiling —** Every 5th interaction (tracked via a durable, server-side counter — see §8), the system triggers an asynchronous Supabase Edge Function to fetch the last 5 interactions, extract thematic interest metrics, and update the user\_interests table without blocking the main chat response stream.
*   **FR-04: Personalized Injection —** After intent is locked, the system fetches the user's interest\_vector from Supabase and injects it into the generation system prompt only, to influence response substance (not format).
*   **FR-05: Observability via LangSmith —** Every request must be traced end-to-end (classification call, retrieval call, generation call, async profiling job) using LangSmith, with a trace\_id propagated through all stages and returned in the response metadata. See §10.
*   **FR-06: Validation-Ready Schema (NEW) —** The response payload and storage layer must reserve structurally compatible fields for future epistemic validation scores (see §14) so that the Epistemological Validation Layer can be switched on later as a non-breaking, additive change rather than a schema migration under pressure.

# 4\. Build Sequence & Phased Rollout (NEW)

This section resolves the sequencing ambiguity raised in review: the validation layer must never be built ahead of, or in parallel with instability in, the core generation pipeline. The three phases below are strictly ordered — each phase's exit criteria must be met before the next begins.

## Phase 1 — Core Pipeline (build first)

The orchestration pipeline (LangChain / LangGraph) must reliably execute end-to-end before any validation work starts:

*   Route the incoming query to the correct intent using the Call 1 classifier (§5).
*   Execute vector retrieval against the historical corpus.
*   Feed context to Qwen 3B (via Ollama) and generate a baseline text response.

**Exit criteria:** Classification, retrieval, and generation run locally and reliably, end to end, without the validation layer involved at all.

## Phase 2 — Validation Plumbing (build second)

Once generation is reliable, add a dummy/no-op validation function immediately after the generation step. This is a structural exercise, not a scoring exercise — its only job is to prove the API payload and downstream UI can carry the new epistemic\_score fields without breaking anything.

**Exit criteria:** Dummy scores flow from backend to frontend on every response, and the chat interface renders correctly with those placeholder fields present.

## Phase 3 — Real Validation Checks (build last)

Only after Phases 1 and 2 are stable does the team wire up the real checks: NLI/consistency models and rule-based logic replace the dummy scores. Full technical design for this phase is intentionally out of scope here — see §14.

**Exit criteria:** Real epistemic scores replace dummy values with no regression to latency budgets defined in §12.

## 4.1 Phase Ownership

| Phase | Primary Owner(s) | Depends On |
| --- | --- | --- |
| 1 — Core Pipeline | Ujjwal (backend/orchestration), Suraj (classifier logic) | — |
| 2 — Validation Plumbing | Ujjwal | Phase 1 exit criteria met |
| 3 — Real Validation Checks | Suraj (models), Ishani (rule-based logic / UI) | Phase 2 exit criteria met |

# 5\. Classification Mechanism

This section resolves the ambiguity around how classification and its confidence score are actually produced.

## 5.1 Architecture

Classification is a separate, lightweight LLM call, distinct from the generation call:

| Call | Purpose | Input | Budget |
| --- | --- | --- | --- |
| Call 1 — Classifier | Produce intent_label + confidence_score | User query only (no history, no interest_vector) | Counted against the 200ms Router budget |
| Call 2 — Generator | Produce final response | Intent framing + retrieved context + interest_vector | Counted against the 800ms Inference budget |

These are two distinct inference passes on Qwen 3B. The 200ms router budget assumes a short, constrained-output classification prompt (low max\_tokens, sampling temperature > 0.1 not used) so latency stays well under the generation call.

## 5.2 Prompt Design

The classifier prompt uses a fixed few-shot template with labeled examples for each of the three classes (examples to be finalized against the benchmark dataset in §13, not hardcoded here). The prompt instructs the model to return only a JSON object:

{  
"intent\_label": "factual | creative\_story | philosophical",  
"confidence\_score": 0.0  
}

## 5.3 Confidence Score Definition

confidence\_score is not a free-text number the model invents. It must be computed by one of the following, to be selected during implementation and logged in LangSmith for comparison:

*   **Option A — Logprob margin:** Using vLLM/Ollama logprob output, compute the normalized margin between the top-1 and top-2 class token probabilities. Higher margin → higher confidence.
*   **Option B — Self-consistency voting:** Sample the classifier k=3 times at low temperature; confidence = (votes for majority label) / k.

Option A is preferred for latency (single forward pass); Option B is the fallback if logprob access is unavailable in the serving stack. This decision must be confirmed during implementation, not left open at runtime.

## 5.4 Malformed Output

If Call 1 fails to return valid JSON (see §10), the system does not retry — it falls through directly to the Malformed JSON fallback (§10).

# 6\. Decision Hierarchy: Intent vs. Interest

1.  **Intent (Hard Rule):** The classification pipeline (factual | creative\_story | philosophical) determines the format of the response. Immutable once set.
2.  **Interest (Soft Flavor):** The user's interest\_vector influences substance (topic focus, narrative themes, tone), but cannot change pipeline format.

## 6.1 Required Execution Sequence

To guarantee FR-02's isolation is never silently violated by FR-04's injection, the pipeline must execute in this strict order:

1\. Receive query  
2\. Call 1 (Classifier) — query ONLY, no interest\_vector, no history  
\-> intent\_label, confidence\_score  
3\. Apply confidence threshold (§10 Ambiguity rule) -> lock final intent\_label  
4\. Fetch interest\_vector from Supabase (parallel-safe with step 5)  
5\. Vector retrieval against historical\_corpus (parallel-safe with step 4)  
6\. Construct generation system prompt:  
\[intent framing - hard, from step 3\]  
\+ \[retrieved context - from step 5\]  
\+ \[interest\_vector - soft, from step 4\]  
7\. Call 2 (Generator) -> response  
8\. Validate response against Pydantic schema  
9\. Return response; increment interaction counter; if counter % 5 == 0,  
enqueue async profiling job (non-blocking)

**Guarantee:** Step 2's prompt template must never contain an interest\_vector field. This should be enforced with a unit test that asserts the classifier prompt builder function has no code path that accepts or interpolates interest\_vector. Steps 4 and 5 can run concurrently to help meet the combined latency budget.

# 7\. Async Batch Profiling — Consistency Guarantees

To prevent race conditions and duplicate processing identified in review:

*   **Durable counter:** Interaction count is tracked server-side via an atomic increment (Postgres UPDATE ... SET interaction\_count = interaction\_count + 1 RETURNING interaction\_count) on user\_profiles, never via client-side or stateless modulo logic.
*   **Idempotency key:** Each Edge Function invocation is keyed by (user\_id, batch\_index) where batch\_index = floor(interaction\_count / 5). The Edge Function checks the profiling\_jobs table (§9.2) with a unique constraint on (user\_id, batch\_index) before processing; if a row already exists, the invocation is a no-op.
*   **No overlap:** Because batch\_index only changes once per 5 interactions and the unique constraint prevents duplicate rows, two concurrent triggers for the same batch cannot both write.
*   **Non-blocking:** The Edge Function call is fire-and-forget relative to the chat response stream; failures in profiling must never affect or delay the user-facing response.

**In plain terms:** profiling\_jobs acts as a bouncer with a clipboard: whenever a background math job wakes up, it must first write (user\_id, batch\_index) to this table. The unique constraint rejects a second write for the same batch, so a double-trigger (e.g. a rapid retry) can only ever update the user's interest weights once.

# 8\. Data Model — Supabase Schema (NEW)

This formalizes exactly which tables support the Intent Classifier and async profiling pipeline, given that user\_profiles already exists and generated stories/chat turns are already persisted. Two new tables are required, plus one additive column on the existing story/chat table. No new tables are required for the validation layer at this stage — see §14 for why that is deliberately deferred.

## 8.1 user\_interests — smoothed interest weights

Holds the thematic weights that Ujjwal injects into the Qwen 3B system prompt (FR-04), written by Suraj's async Edge Function every 5 interactions (FR-03).

CREATE TABLE user\_interests (  
user\_id UUID PRIMARY KEY REFERENCES user\_profiles(id) ON DELETE CASCADE,  
factual\_weight DECIMAL(3,2) DEFAULT 0.33 NOT NULL,  
creative\_weight DECIMAL(3,2) DEFAULT 0.33 NOT NULL,  
philosophical\_weight DECIMAL(3,2) DEFAULT 0.33 NOT NULL,  
last\_computed\_counter INT DEFAULT 0 NOT NULL,  
updated\_at TIMESTAMPTZ DEFAULT NOW() NOT NULL,  
  
CONSTRAINT check\_factual\_bounds CHECK (factual\_weight BETWEEN 0.0 AND 1.0),  
CONSTRAINT check\_creative\_bounds CHECK (creative\_weight BETWEEN 0.0 AND 1.0),  
CONSTRAINT check\_philosophical\_bounds CHECK (philosophical\_weight BETWEEN 0.0 AND 1.0)  
);  
  
CREATE INDEX idx\_user\_interests\_lookup ON user\_interests(user\_id);

## 8.2 profiling\_jobs — idempotency lock

Exists purely to guarantee the Edge Function processes a given 5-turn batch exactly once (§7).

CREATE TABLE profiling\_jobs (  
id BIGSERIAL PRIMARY KEY,  
user\_id UUID REFERENCES user\_profiles(id) ON DELETE CASCADE NOT NULL,  
batch\_ceiling INT NOT NULL,  
status VARCHAR(20) DEFAULT 'pending' NOT NULL,  
created\_at TIMESTAMPTZ DEFAULT NOW() NOT NULL,  
  
CONSTRAINT unique\_user\_batch UNIQUE (user\_id, batch\_ceiling)  
);

## 8.3 Additive column on the existing story/chat table

The Edge Function needs to know what the user's recent queries were classified as in order to compute the batch weights. Rather than a new logging table, the existing generated\_stories (or equivalent chat history) table needs one additional column:

ALTER TABLE generated\_stories  
ADD COLUMN intent\_label VARCHAR(50); -- factual | creative\_story | philosophical

**Deliberately deferred:** The epistemic score columns (sabda\_score, anumana\_score, pratyaksa\_score, upamana\_score, final\_confidence, bias\_flagged) and the isolated trusted\_sources fact table are NOT created in this phase. They belong to the Epistemological Validation Layer (§14) and should only be migrated in once that spec is finalized — see Open Item #6.

## 8.4 Table Responsibilities Summary

| Table | Written By | Read By | Purpose |
| --- | --- | --- | --- |
| user_interests | Async profiling Edge Function (every 5th turn) | Generation service (Call 2 prompt injection) | Smoothed thematic weight per user |
| profiling_jobs | Async profiling Edge Function | Async profiling Edge Function (self-check) | Idempotency lock, one row per (user_id, batch) |
| generated_stories.intent_label | Main chat pipeline, every turn | Async profiling Edge Function | Source data the weight math is computed from |

# 9\. Edge Cases & Error Handling

*   **Ambiguity:** If confidence\_score < 0.70, default to factual (RAG), not philosophical.

_Rationale (revised from v1): philosophical is the most compute-intensive pipeline (retrieval + analytical synthesis framing). Routing low-confidence — i.e., least predictable — traffic to the most expensive, least latency-predictable pipeline compounds risk under load. factual is grounded, cheaper, and lower-hallucination-risk, making it the safer default when the model itself is unsure. This is a recommended change from v1 and should be confirmed with stakeholders before sign-off, since it alters runtime behavior, not just spec clarity._

*   **Malformed JSON:** If Qwen 3B fails to output valid JSON at either Call 1 or Call 2, default to standard factual RAG response.
*   **Network/Timeout:** If local inference fails entirely, fail-safe to a cached standard "I'm experiencing a temporary processing issue" message.
*   **Vector Retrieval Failure:** If retrieval against historical\_corpus fails, times out (>150ms), or returns zero/low-similarity matches:
    *   The request does not fail. Generation proceeds without retrieved context (ungrounded).
    *   metadata.retrieval\_status is set to "degraded" in the response so downstream consumers/analytics can distinguish grounded vs. ungrounded answers.
    *   This is distinct from the full inference-failure fallback above — retrieval degradation alone should not trigger the cached error message.

# 10\. Observability & Tracing — LangSmith

LangSmith is introduced as the tracing backbone for this pipeline:

*   Every request generates a single root trace covering: Call 1 (classifier), retrieval call, Call 2 (generator), and Pydantic validation step.
*   The async profiling job (§7) is logged as a separate, linked trace (tagged with the same user\_id and batch\_index) so profiling runs can be audited independently of chat latency.
*   Each trace is tagged with: intent\_label, confidence\_score, retrieval\_status, and which fallback path (if any) was triggered.
*   trace\_id is propagated through the pipeline and included in the API response metadata (see §11) so support/debugging can pull the exact trace for any user-reported issue.
*   LangSmith traces are the primary input for monitoring classification drift over time and for auditing the 95% accuracy claim in §15 against production traffic, not just the static benchmark set.

# 11\. API Contracts (Input → Output)

### Input Schema (/chat POST)

{  
"user\_id": "UUID",  
"query": "string"  
}

### Output Schema (Response)

{  
"response": "string",  
"intent\_label": "factual | creative\_story | philosophical",  
"metadata": {  
"pipeline\_used": "RAG | Creative | Philosophical",  
"retrieval\_status": "ok | degraded",  
"trace\_id": "string"  
}  
}

**Forward-compatibility note (FR-06):** From Phase 2 onward (§4), metadata will additionally carry placeholder epistemic\_score fields (initially dummy values). This is an additive field, not a breaking change — clients that ignore unknown fields require no update.

# 12\. Constraints

*   **Latency Budget:** Total round trip must occur in < 1.5s.
    *   Router Logic (Call 1, classification): < 200ms
    *   Vector Retrieval: < 150ms
    *   Inference (Call 2, generation): < 800ms
    *   Network/Overhead: < 350ms
*   **Inference Engine:** All inference must occur on-premise using Qwen 3B (via local Ollama/vLLM).
*   **Schema Enforcement:** All LLM outputs (both Call 1 and Call 2) must be strictly validated using Pydantic.

# 13\. Epistemological Validation Layer (Planned — Phase 3)

**Scope note:** This section is intentionally kept at a product/architecture level. Detailed algorithm design, model fine-tuning, scoring thresholds, and the trusted-sources corpus design will be covered in a dedicated Validation Layer spec, once Phases 1 and 2 (§4) are complete. Nothing here should be treated as an implementation instruction yet.

## 13.1 Purpose

Once the core pipeline is stable, each generated response will be checked along four validation axes, inspired by the four Pramāṇas (means of valid knowledge): Śabda (source/testimony), Anumāna (logical inference/consistency), Pratyakṣa (direct evidence/contradiction), and Upamāna (comparison/cultural-contextual fit). Together these produce a confidence score and a bias flag attached to the response.

## 13.2 Where it sits in the pipeline

The validation step runs after Call 2 (Generator), on the already-generated response text. In Phase 2 this position is occupied by a dummy function only (§4); real scoring logic is added in Phase 3 without moving this position in the pipeline.

## 13.3 High-level model approach

Validation is expected to run on a separate, lightweight model isolated from the generation model, to protect the platform's latency budget (§12) — generation is a heavier decoder-only pass, while validation is expected to be a fast classification-style pass over already-generated text. Whether an existing on-server model is reused for this or a new one is sourced is an open item (see Open Items, #5) and will be resolved in the dedicated Validation Layer spec, not here.

## 13.4 Data dependency

The Śabda (source) check will require an isolated, curated corpus of verified reference material, kept separate from the platform's own generated-story corpus — checking a generated story against other generated stories would let the system validate itself against its own fiction. The exact shape of this corpus is out of scope for this document.

## 13.5 Output contract (reserved, not yet populated)

The response metadata will eventually carry: intent\_label, sabda\_score, anumana\_score, pratyaksa\_score, upamana\_score, final\_confidence, and bias\_flagged. These fields are reserved structurally per FR-06 and §11, but are not scored for real until Phase 3 is designed and implemented.

# 14\. Acceptance Criteria

*   **Classification Accuracy:** \> 95% accuracy on the historical query benchmark dataset, cross-validated against live LangSmith-traced production data on a rolling basis.
*   **Profiling Consistency:** User interest metrics must correctly identify dominant themes across a 5-turn window, with zero duplicate-processed batches (verified via the profiling\_jobs uniqueness constraint, §7).
*   **Pipeline Logic:**
    *   **factual →** Performs vector search in historical\_corpus + injects context.
    *   **creative\_story →** Performs vector search for historical facts + injects creative framing.
    *   **philosophical →** Performs retrieval + injects analytical synthesis framing.
*   **Isolation Guarantee:** Automated test confirms the classifier prompt builder has no code path through which interest\_vector can enter Call 1.
*   **Phase Gating (NEW):** Phase 2 and Phase 3 (§4) cannot begin until the exit criteria of the preceding phase are demonstrably met, not just self-reported as done.

# Open Items Requiring Stakeholder Sign-off

1.  Confirm confidence-score method: logprob margin (Option A) vs. self-consistency voting (Option B) — §5.3.
2.  Confirm change of ambiguity default from philosophical → factual — §9.
3.  Finalize few-shot classification examples against the benchmark dataset — §5.2.
4.  Confirm phased rollout ownership and exit criteria per phase — §4.1.
5.  Confirm whether an existing on-server model is reused for the validation layer's checks, or whether a new model needs to be sourced/fine-tuned — to be resolved in the dedicated Validation Layer spec (§13.3).
6.  Confirm timing of the epistemic-score schema migration: added as nullable/dummy columns during Phase 2, or deferred entirely until Phase 3 begins — §8.3.