# Implementation Plan — Feature 01: Core Infrastructure & Data Contracts (Chunk 1)

**Source spec:** `.claude/specs/feature-01_spec_core_infrastructure.md` (v1.0)
**Target branch:** `feature/infrastrcture_development`
**Status:** Awaiting approval — do not implement until sign-off.

---

## Context

The MyItihas platform needs a type-safe backend foundation before any of the
two-stage inference pipeline (Intent Classification → Generation) can be built.
Today the repo has the *directory skeleton only*: `server/main.py` is a bare
`app = FastAPI()`, `backend/inference/client.py` is a one-line comment,
`schemas/` is empty, `requirements.txt` is empty, and the `myenv` virtualenv has
nothing installed but `pip`/`setuptools` (so the app cannot even boot). This
feature fills in that foundation: dependency management, strict Pydantic v2
request/response contracts, a stateless local-inference transport wrapper with
hard latency enforcement, and a `/chat` route that wires them together with the
required error handling. Getting the data contracts and timeout semantics right
now is what prevents classifier/generator data drift and latency-budget
violations later.

### Current state (verified)
| Path | State |
| --- | --- |
| `server/main.py` | `from fastapi import FastAPI; app = FastAPI()` — no routes |
| `server/api/` | empty package (`__init__.py`, `.gitkeep`) |
| `schemas/` | empty package (`__init__.py`, `.gitkeep`) — **no `models.py`** |
| `backend/inference/client.py` | comment stub only |
| `backend/database/*`, `backend/routing/*` | comment stubs — **out of scope for Chunk 1** |
| `requirements.txt` | empty |
| `.env` | has `SUPABASE_URL`, `SUPABASE_KEY`, `LOCAL_MODEL_ENDPOINT` |
| `myenv` | only `pip`, `setuptools` installed |

### Scope guardrails
- **In scope:** FR-01 scaffolding gaps, FR-02 schemas, FR-03 inference wrapper,
  FR-04 timeout enforcement, `/chat` route + error handling, tests.
- **Out of scope (later chunks):** real Ollama/vLLM classification & generation
  logic, LangGraph orchestration (`backend/routing/*`), Supabase/database
  (`backend/database/*`), RAG retrieval, async profiling, LangSmith tracing.
  The `/chat` route in this chunk returns a schema-valid response via a stubbed
  pipeline so the contract and error paths can be tested end to end.

---

## Task Breakdown

### Task 0 — Dependencies & environment
**Files:** `requirements.txt` (fill), install into `myenv`.
- Pin: `fastapi`, `uvicorn[standard]`, `pydantic>=2`, `pydantic-settings`,
  `httpx` (async inference calls + `TestClient`), `python-dotenv`,
  `pytest`, `pytest-asyncio`.
- Install with `./myenv/bin/pip install -r requirements.txt`.

**Prerequisites:** none.
**Verification:**
- `./myenv/bin/pip list` shows the pinned packages.
- `./myenv/bin/python -c "import fastapi, pydantic, httpx, uvicorn"` exits 0.
- `python -c "import pydantic; assert pydantic.VERSION.startswith('2')"`.

---

### Task 1 — Config loader
**Files:** `backend/config.py` (new).
- `Settings` via `pydantic-settings` reading `LOCAL_MODEL_ENDPOINT`
  (and Supabase vars, unused this chunk but loaded) from `.env`.
- Expose latency budget constants: `CLASSIFY_TIMEOUT_MS = 200`,
  `GENERATE_TIMEOUT_MS = 800`.

**Prerequisites:** Task 0.
**Verification:** `./myenv/bin/python -c "from backend.config import settings; print(settings.local_model_endpoint)"` prints the `.env` value without error.

---

### Task 2 — Pydantic v2 schemas (FR-02, §3)
**Files:** `schemas/models.py` (new).
- `IntentLabel` str-Enum: `factual | creative_story | philosophical`.
- `PipelineUsed` str-Enum: `RAG | Creative | Philosophical`.
- `RetrievalStatus` str-Enum: `ok | degraded`.
- `EpistemicScores` model: keys `source`, `logic`, `contradiction`, `culture`
  (all `Optional[float]`).
- `GenerationMetadata`: `pipeline_used`, `retrieval_status`, `trace_id` (str/UUID),
  `epistemic_scores: Optional[EpistemicScores] = None`,
  `bias_flagged: bool = False`.
- `ChatRequest`: `user_id: UUID`, `query: str` (min_length=1).
- `ChatResponse`: `response: str`, `intent_label: IntentLabel`,
  `metadata: GenerationMetadata`.
- Use `model_config = ConfigDict(extra="forbid")` on request for strictness.

**Prerequisites:** Task 0.
**Verification:**
- `ChatRequest(user_id="not-a-uuid", query="x")` raises `ValidationError`.
- `ChatResponse(...).model_dump()` includes `epistemic_scores: None` and
  `bias_flagged: False` (null fields serialized, not dropped) → satisfies AC-4.

---

### Task 3 — Inference client wrapper (FR-03, FR-04, §4, §5)
**Files:** `backend/inference/client.py` (replace stub).
- `async def llm_call(prompt: str, *, timeout_ms: int) -> str` — **stateless**,
  no session state (Constraint §Isolation).
- POST to `settings.local_model_endpoint` via `httpx.AsyncClient` with
  `timeout=timeout_ms/1000`.
- On `httpx.TimeoutException` → raise `TimeoutError`.
- On `httpx.ConnectError`/unreachable → raise `ConnectionError`.
- Provide thin helpers `classify_call(prompt)` and `generate_call(prompt)` that
  pass `CLASSIFY_TIMEOUT_MS` / `GENERATE_TIMEOUT_MS`.
- No JSON parsing/retry here — malformed handling lives in the orchestrator (§5).

**Prerequisites:** Tasks 0, 1.
**Verification:**
- Unit test with a monkeypatched client that sleeps > budget → `llm_call`
  raises `TimeoutError` (AC-3, the deliberate sleep test).
- Unit test with an unreachable endpoint → raises `ConnectionError`.
- Grep/inspection confirms no module-level/global session cache (statelessness).

---

### Task 4 — `/chat` route + error handling (§5, AC-1, AC-2)
**Files:** `server/api/chat.py` (new router), `server/main.py` (include router +
exception handlers).
- `POST /chat` typed with `ChatRequest` → `ChatResponse`.
- Stubbed orchestrator for this chunk: returns a valid `ChatResponse`
  (fixed `intent_label`, generated `trace_id`, `retrieval_status="ok"`).
- Exception handlers:
  - `TimeoutError` → `503` (Inference Timeout).
  - `ConnectionError` → `503` with `"System temporarily busy"`.
  - Malformed classifier JSON → no retry; log via logger + return fallback
    factual response (wired as a helper now, exercised fully in a later chunk).
- FastAPI's built-in validation yields `422` automatically for bad bodies (AC-2).

**Prerequisites:** Tasks 2, 3.
**Verification:**
- `uvicorn server.main:app` boots; `GET /docs` lists `POST /chat` (AC-1).
- `TestClient` POST with missing/invalid `user_id` → `422` (AC-2).
- `TestClient` POST valid body → `200` with all metadata fields present incl.
  nulls (AC-4).
- Simulated `TimeoutError` from the pipeline → `503` (AC-3 end-to-end).

---

### Task 5 — Test suite
**Files:** `tests/test_schemas.py`, `tests/test_inference_client.py`,
`tests/test_chat_route.py` (new), plus `tests/__init__.py`.
- Consolidate the verification checks above into `pytest` cases.
- Map explicitly to Acceptance Criteria 1–4.

**Prerequisites:** Tasks 1–4.
**Verification:** `./myenv/bin/pytest -q` → all green.

---

## Dependency Graph
```
Task 0 (deps)
  ├─> Task 1 (config) ─┐
  ├─> Task 2 (schemas) ─┼─> Task 4 (route) ─> Task 5 (tests)
  └─> Task 3 (client) ──┘
        (Task 3 also needs Task 1)
```

## Acceptance Criteria Traceability
| Spec AC | Covered by |
| --- | --- |
| AC-1 App Initialization (boots, routes defined) | Task 4 |
| AC-2 Schema Validation (422 on bad body) | Tasks 2, 4 |
| AC-3 Inference Latency (sleep test raises) | Tasks 3, 4 |
| AC-4 Data Integrity (null metadata serialized) | Tasks 2, 4 |

## End-to-End Verification
1. `./myenv/bin/pip install -r requirements.txt`
2. `./myenv/bin/pytest -q` → all pass.
3. `./myenv/bin/uvicorn server.main:app --reload`, open `/docs`, confirm
   `POST /chat` present; send a sample body and confirm the response matches
   `ChatResponse` with null `epistemic_scores` and `bias_flagged=false`.

## Open Questions / Assumptions
- **Stubbed pipeline:** Chunk 1 has no real Ollama call in the `/chat` path;
  the route returns a schema-valid canned response so contracts + error paths
  are testable. Real inference lands in a later chunk. (Assumed from "Chunk 1"
  framing — flag if you want a live Ollama call wired now.)
- **Timeout enforcement** is via `httpx` client timeout (network-level). If you
  want wall-clock enforcement around arbitrary local calls too, say so and I'll
  add an `asyncio.wait_for` guard.
- `backend/database/*` and `backend/routing/*` stubs are left untouched.
