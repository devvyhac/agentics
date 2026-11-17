---
title: 'Unified FastAPI Gateway and Baseline Generalist AI Agent'
type: 'feature'
created: '2026-11-17'
status: 'done'
baseline_commit: 'NO_VCS'
route: 'dispatch'
review_loop_iteration: 0
context: []
---

<frozen-after-approval reason="human-owned intent — do not modify unless human renegotiates">

## Intent

**Problem:** The system requires an isolated, production-ready AI agent service adhering to the external marketplace webhook contract (kavver runner) with strict runtime guardrails for timeout buffering and word-count governance.

**Approach:** Build a unified FastAPI gateway mounting isolated per-agent routers, and deliver the baseline Generalist Agent (`agents/generalist`) powered by an OpenAI-compatible client, robust sentence-aware word trimming, defensive timeout management, and comprehensive local test verification.

## Boundaries & Constraints

**Always:**
- Keep all agent-specific logic, config, schemas, prompts, and services strictly contained within `agents/generalist/` without inter-agent coupling.
- Adhere strictly to the marketplace webhook contract: incoming `POST /{agent_prefix}/webhook` (`id`, `match_id`, `type`, `category`, `prompt`, `max_words`, `timeout_seconds`) and outgoing payload (`match_id`, `output_text`, `word_count`, `model_tag`).
- Compute `word_count` strictly as `len(output_text.split())` ensuring `word_count <= max_words`.
- Compute `effective_timeout = max(1.0, timeout_seconds - INTERNAL_TIMEOUT_SAFETY_BUFFER_SECONDS)` and defensively handle timeouts with a graceful fallback response instead of dropping connections.
- Support universal OpenAI-compatible backends (`AsyncOpenAI`) configurable via environment variables (`LLM_BASE_URL`, `LLM_API_KEY`, `LLM_MODEL_NAME`, `MODEL_TAG`).

**Never:**
- Never introduce shared state, inter-agent communication, or swarm mechanics between agents.
- Never exceed `max_words` in the final `output_text`.
- Never let unhandled LLM network exceptions or timeouts crash the server process or return unformatted 500 responses without JSON payload.

## I/O & Edge-Case Matrix

| Scenario | Input / State | Expected Output / Behavior | Error Handling |
|----------|--------------|---------------------------|----------------|
| Health Probe | `GET /generalist/health` | HTTP 200 `{"status": "ok", "agent": "generalist"}` | N/A |
| Valid Webhook Request | `POST /generalist/webhook` with valid JSON within word/timeout limits | HTTP 200 with matching `match_id`, generated `output_text`, `word_count <= max_words`, and `model_tag` | N/A |
| Word Count Overflow | LLM produces more words than `max_words` | Output trimmed to sentence boundary or clean word slice with ellipsis, `word_count <= max_words` | Truncate cleanly, return HTTP 200 |
| Timeout Limit Approaching | LLM call duration exceeds `effective_timeout` | Catch `asyncio.TimeoutError`, return fallback completion with matching `match_id` | HTTP 200 with fallback message, no server hang |
| Invalid Request Body | Missing required fields or negative numbers | HTTP 422 Unprocessable Entity with standard FastAPI error details | FastAPI validation error |

</frozen-after-approval>

## Code Map

- `requirements.txt` -- Project dependencies: `fastapi`, `uvicorn[standard]`, `pydantic`, `pydantic-settings`, `openai`, `python-dotenv`, `pytest`, `pytest-asyncio`, `httpx`.
- `main.py` -- Unified FastAPI gateway server mounting agent routers and defining global exception handlers.
- `agents/generalist/__init__.py` -- Package marker for Generalist agent module.
- `agents/generalist/.env.example` -- Agent environment template with model config, safety buffer, and webhook secret.
- `agents/generalist/config.py` -- Pydantic `BaseSettings` loader for typed configuration.
- `agents/generalist/schemas.py` -- Pydantic request and response models matching marketplace contract.
- `agents/generalist/prompts.py` -- Generalist persona system prompts and word-count directives.
- `agents/generalist/service.py` -- Universal `AsyncOpenAI` client wrapper, timeout guardrail, and sentence-aware post-processor.
- `agents/generalist/router.py` -- APIRouter defining `POST /webhook` and `GET /health`.
- `tests/test_generalist.py` -- Unit and integration tests for health check, webhook contract, timeout fallback, and word-trimming logic.

## Tasks & Acceptance

**Execution:**
- [x] `requirements.txt` -- Create requirements file with core dependencies -- Establish runtime dependencies for FastAPI, OpenAI SDK, Pydantic, and testing.
- [x] `agents/generalist/.env.example` -- Create agent environment template -- Document required configuration variables with clear defaults.
- [x] `agents/generalist/config.py` -- Implement typed settings loader with Pydantic BaseSettings -- Allow environment variable loading with sensible fallbacks.
- [x] `agents/generalist/schemas.py` -- Implement Pydantic request and response models -- Validate inbound marketplace payload and serialize outbound response.
- [x] `agents/generalist/prompts.py` -- Define generalist system prompt templates -- Guide LLM execution for high-quality generalist responses within word bounds.
- [x] `agents/generalist/service.py` -- Implement LLM invocation service, timeout guardrail, and word-count trimming -- Ensure reliable execution and strict compliance with limits.
- [x] `agents/generalist/router.py` -- Implement APIRouter with `/webhook` and `/health` -- Expose HTTP endpoints under the generalist prefix.
- [x] `main.py` -- Create root FastAPI gateway application -- Mount `/generalist` router and configure root health check and metadata.
- [x] `tests/test_generalist.py` -- Create comprehensive test suite -- Verify health probe, request validation, word trimming, and timeout handling.

**Acceptance Criteria:**
- Given the FastAPI gateway running, when `GET /generalist/health` is requested, then HTTP 200 `{"status": "ok", "agent": "generalist"}` is returned.
- Given a valid incoming webhook payload with `max_words=50`, when processed by the generalist service, then the resulting `output_text` has `word_count <= 50` matching `len(output_text.split())`.
- Given a slow or hanging LLM completion, when processing exceeds `effective_timeout`, then a graceful fallback payload is returned with the matching `match_id` without dropping the HTTP connection.
- Given the test suite executed with `pytest`, then all tests pass with zero errors.

## Implementation Notes

- Configured Python 3.12 virtual environment via `uv` to ensure prebuilt wheel compatibility on Windows.
- Implemented sentence-aware word count trimmer strictly checking trailing 20% candidate length for terminators (`.`, `!`, `?`) and appending `...` with guaranteed `word_count <= max_words`.
- Configured defensive timeout management with `effective_timeout = max(1.0, timeout_seconds - internal_timeout_safety_buffer_seconds)` and fallback generation.
- Added comprehensive unit and integration test suite covering health probes, contract conformance, word count trimming, and timeout fallback. All 13 tests pass.

## Spec Change Log

## Review Triage Log

- `agents/generalist/router.py`: `medium` -- Instantiating `GeneralistService` on every request creates client and HTTP connection churn; route to patch to use cached/singleton service.
- `agents/generalist/service.py`: `medium` -- When `timeout_seconds` is very small, `effective_timeout` could equal or exceed total timeout; route to patch to ensure `effective_timeout < timeout_seconds`.
- `agents/generalist/service.py`: `low` -- Empty or whitespace-only LLM output returns 0 words without fallback; route to patch to trigger fallback text.
- `main.py`: `low` -- Generic exception handler leaks raw exception string; route to patch to sanitize 500 error response.
- `main.py`: `low` -- Unused `RequestValidationError` import; route to patch to remove.
- `tests/test_generalist.py`: `medium` -- Verification gap: missing tests for `get_service()`, root `GET /`, and unhandled 500 handler; route to patch to add test coverage.
- `agents/generalist/service.py`: `low` -- Not passing token ceiling to OpenAI completion wastes tokens when `max_words` is small; route to patch to cap tokens.
- `agents/generalist/config.py`: `low` -- Unenforced optional `webhook_secret`; reject as optional per brainstorm intent and marketplace webhook contract.

## Design Notes

Sentence-aware word trimmer logic:
1. Split `words = text.strip().split()`.
2. If `len(words) <= max_words`, return original text and `len(words)`.
3. If `len(words) > max_words`, inspect `candidate = " ".join(words[:max_words])`.
4. Search backwards from candidate end for sentence terminators (`.`, `!`, `?`). If found within the last 20% of candidate length, slice to terminator.
5. If no terminator found, slice at `max_words` and append `...`.
6. Compute final `word_count = len(final_text.split())`.

## Verification

**Commands:**
- `uv run pytest tests/test_generalist.py -v` -- expected: All unit and integration tests pass.
- `uv run python -c "import main; print(main.app.title)"` -- expected: Application imports and initializes cleanly.
