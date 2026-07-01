# Specification: Core Infrastructure & Data Contracts (Chunk 1)

**Status:** Ready for Implementation | **Version:** 1.0
**Project:** MyItihas Platform

## 1. Problem Statement
The current platform requires a robust, type-safe backend foundation to support the two-stage inference pipeline (Intent Classification -> Generation). We lack standardized project scaffolding, request/response validation, and a reliable transport layer for local LLM inference. This leads to high risk of data inconsistency between the classifier and the generator.

## 2. Functional Requirements
* **FR-01 (Project Scaffolding):** Initialize a FastAPI application with a modular directory structure (`/schemas`, `/backend`, `/server`).
* **FR-02 (Type Safety):** Implement strict Pydantic schemas for all API inputs and outputs to ensure data integrity.
* **FR-03 (Inference Wrapper):** Create a centralized client wrapper for Ollama/vLLM that manages the inference request lifecycle.
* **FR-04 (Timeout Management):** Implement mandatory latency enforcement. The client must raise an exception if the inference call exceeds the pre-defined budget (200ms for Classify, 800ms for Generate).

## 3. API Contracts
All communication must strictly follow the schema defined below.

### 3.1 Input Schema (`ChatRequest`)
- `user_id` (UUID): Unique identifier for the user.
- `query` (string): The user's input text.

### 3.2 Output Schema (`ChatResponse`)
- `response` (string): The generated text.
- `intent_label` (string): 'factual' | 'creative_story' | 'philosophical'.
- `metadata` (`GenerationMetadata`):
    - `pipeline_used` (string): Enum (RAG | Creative | Philosophical).
    - `retrieval_status` (string): 'ok' | 'degraded'.
    - `trace_id` (string): UUID.
    - `epistemic_scores` (dict/optional): Keys: `source`, `logic`, `contradiction`, `culture`. (Default to None).
    - `bias_flagged` (bool): Default False.

## 4. Constraints
* **Latency:** All internal `llm_call` functions must adhere to the 1.5s total round-trip budget requirement.
* **Tech Stack:** FastAPI, Pydantic (v2), Uvicorn.
* **Deployment:** Inference must be local-only (Ollama/vLLM).
* **Isolation:** The `llm_call` function must not introduce any automatic session management; it must be a stateless transport layer.

## 5. Edge Cases & Error Handling
* **Inference Timeout:** If the LLM exceeds the allocated time (800ms gen / 200ms class), the `llm_call` wrapper must raise a `TimeoutError`, which the server will catch and return a `503 Service Unavailable`.
* **Malformed JSON:** If the Classifier returns non-JSON or invalid JSON, the orchestrator should not retry. Log the malformed output via print/logger and return a fallback response.
* **Connectivity Issues:** If the Ollama/vLLM server is unreachable, raise a `ConnectionError` and return a standard "System temporarily busy" message.

## 6. Acceptance Criteria
1. **App Initialization:** The FastAPI app boots correctly with all routes defined.
2. **Schema Validation:** `POST /chat` returns a `422 Unprocessable Entity` if the JSON body does not match the Pydantic `ChatRequest` schema.
3. **Inference Latency:** A deliberate `sleep` test in the LLM wrapper must demonstrate that it successfully interrupts/raises an error if it exceeds the latency constraint.
4. **Data Integrity:** All metadata fields are serialized in the response, even if they are null/empty.

---

### Instructions for the AI Agent:
- "Please implement this spec in stages. First, generate the folder structure and `requirements.txt`. Then, define the models in `/schemas/models.py`. Finally, build the `inference/client.py` wrapper."