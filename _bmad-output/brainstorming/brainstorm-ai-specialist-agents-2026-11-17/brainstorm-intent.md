# Architecture & Intent Specification: Standalone AI Specialist & Generalist Agents

**Topic:** Modular, Folder-Isolated Specialist and Generalist AI Agent Services  
**Target File:** `brainstorm-intent.md`  
**Date:** 2026-11-17  
**Status:** Approved Intent Specification  

---

## 1. Executive Intent & Architecture Overview

The system delivers a modular ecosystem of standalone AI agents deployed via production HTTP endpoints. The design balances simplicity, scalability, and strict isolation:

* **Unified Gateway Server:** A single FastAPI application acts as the unified HTTP process and router gateway, mounting independent APIRouters from isolated agent directories.
* **Zero Agent Interdependence:** Agents operate with zero swarm mechanics, inter-agent coordination, or shared internal memory state. Each agent represents a pure, isolated execution pipeline capable of servicing independent marketplace tasks.
* **Marketplace Integration Via Webhooks:** The endpoints integrate into external agent marketplaces managed via the `kavver` npm ecosystem package. The marketplace issues a task payload via POST webhook, the agent executes the task according to its persona and constraints, and responds directly with a formatted payload.
* **Standardized Agent Contracts:** Every agent adheres to a common I/O schema, an OpenAI-compatible LLM driver, and strict execution guardrails (timeout buffering and word-count governance).

```
                      +-----------------------------------+
                      | External Agent Marketplace (Kavver)|
                      +-----------------+-----------------+
                                        | POST /{agent}/webhook
                                        v
+-----------------------------------------------------------------------------------+
| FastAPI Unified Gateway (server.py / main.py)                                      |
|                                                                                   |
|  Mounts Routers:                                                                  |
|   ├── /generalist/webhook  --> agents/generalist/router.py                        |
|   ├── /storyteller/webhook --> agents/storyteller/router.py                       |
|   └── /proofreader/webhook --> agents/proofreader/router.py                       |
+-----------------------------------+-----------------------------------------------+
                                    |
            +-----------------------+-----------------------+
            |                                               |
            v                                               v
+--------------------------+                    +--------------------------+
| agents/generalist/       |                    | agents/storyteller/      |
|  - .env.example          |                    |  - .env.example          |
|  - router.py & service.py|                    |  - router.py & service.py|
|  - OpenAI-compatible LLM |                    |  - OpenAI-compatible LLM |
+--------------------------+                    +--------------------------+
```

---

## 2. Agent Directory Layout

The workspace enforces complete directory isolation. The **Generalist Agent** serves as the initial baseline and template. Specialists (**Storyteller**, **Proofreader**) mirror this structure.

```
agentics/
├── main.py                     # Unified FastAPI server mounting per-agent routers
├── requirements.txt            # Project dependencies (fastapi, uvicorn, openai, pydantic, etc.)
├── .env                        # Root / global environment overrides (optional)
│
└── agents/
    ├── generalist/             # Priority 1: Baseline All-Rounder Agent
    │   ├── __init__.py
    │   ├── .env.example        # Local agent configuration contract
    │   ├── config.py           # Typed settings loader
    │   ├── schemas.py          # Marketplace Request & Response Pydantic models
    │   ├── prompts.py          # Generalist system prompts & instructions
    │   ├── service.py          # LLM client invocation, timeout & post-processing logic
    │   └── router.py           # APIRouter exposing /webhook and /health
    │
    ├── storyteller/            # Priority 2: Creative Storytelling Specialist
    │   ├── __init__.py
    │   ├── .env.example
    │   ├── config.py
    │   ├── schemas.py
    │   ├── prompts.py
    │   ├── service.py
    │   └── router.py
    │
    └── proofreader/            # Priority 3: Editorial & Grammar Specialist
        ├── __init__.py
        ├── .env.example
        ├── config.py
        ├── schemas.py
        ├── prompts.py
        ├── service.py
        └── router.py
```

---

## 3. Marketplace Webhook Specification

All agent endpoints consume and produce JSON conforming to the marketplace contract negotiated with the `kavver` npm runner.

### 3.1 Endpoints Exposed per Agent
* `POST /{agent_prefix}/webhook` — Core execution route for incoming tasks.
* `GET /{agent_prefix}/health` — Readiness & liveness probe returning `{ "status": "ok", "agent": "{agent_prefix}" }`.

### 3.2 Inbound Payload Schema (`POST /{agent_prefix}/webhook`)

```json
{
  "id": "req_8f12c34a9b",
  "match_id": "match_90e71ab842",
  "type": "content_generation",
  "category": "general_writing",
  "prompt": "Provide a comprehensive overview of decentralized computing benefits and tradeoffs.",
  "max_words": 350,
  "timeout_seconds": 25
}
```

#### Field Specifications:
| Field | Type | Required | Description |
|---|---|---|---|
| `id` | `string` | Yes | Unique request identifier issued by the marketplace. |
| `match_id` | `string` | Yes | Match/Task session ID to correlate request with response. |
| `type` | `string` | Yes | Task category type descriptor. |
| `category` | `string` | Yes | Granular specialization domain. |
| `prompt` | `string` | Yes | Prompt instructions to be executed by the agent. |
| `max_words` | `integer` | Yes | Hard ceiling for generated output length. |
| `timeout_seconds` | `integer` / `float` | Yes | Maximum time window allocated before marketplace aborts. |

### 3.3 Outbound Response Schema (HTTP 200)

```json
{
  "match_id": "match_90e71ab842",
  "output_text": "Decentralized computing distributes workloads across independent nodes, eliminating single points of failure...",
  "word_count": 312,
  "model_tag": "groq/llama-3.3-70b-versatile"
}
```

#### Field Specifications:
| Field | Type | Description |
|---|---|---|
| `match_id` | `string` | Exact `match_id` reflected from the incoming request. |
| `output_text` | `string` | Final agent output post-processed and trimmed to `max_words`. |
| `word_count` | `integer` | Exact word count calculated on `output_text`. |
| `model_tag` | `string` | Model identifier string documenting backend provider and model used. |

---

## 4. Model Flexibility & Configuration Contract

To maximize provider flexibility and prevent vendor lock-in, agents interact with LLMs using an OpenAI-compatible universal client interface (`openai.AsyncOpenAI`). This allows any backend to be plugged in via configuration alone (e.g., Groq, NVIDIA NIM, DeepSeek, Together AI, OpenRouter, or local Ollama).

### 4.1 Per-Agent Configuration Contract (`.env.example`)

Each agent folder maintains its own isolated `.env.example`:

```env
# Agent Model & Provider Configuration
AGENT_NAME=generalist
MODEL_TAG=groq/llama-3.3-70b-versatile
LLM_BASE_URL=https://api.groq.com/openai/v1
LLM_API_KEY=gsk_your_api_key_here
LLM_MODEL_NAME=llama-3.3-70b-versatile

# Execution & Safety Parameters
LLM_TEMPERATURE=0.7
LLM_MAX_TOKENS=2048
INTERNAL_TIMEOUT_SAFETY_BUFFER_SECONDS=2.5

# Marketplace Security
WEBHOOK_SECRET=your_optional_shared_secret_here
```

### 4.2 Supported Model Backends
* **Groq:** `LLM_BASE_URL=https://api.groq.com/openai/v1`
* **NVIDIA NIM:** `LLM_BASE_URL=https://integrate.api.nvidia.com/v1`
* **DeepSeek:** `LLM_BASE_URL=https://api.deepseek.com/v1`
* **Together AI:** `LLM_BASE_URL=https://api.together.xyz/v1`
* **Local Ollama:** `LLM_BASE_URL=http://localhost:11434/v1` (with `LLM_API_KEY=ollama`)

---

## 5. Execution Guardrails

Every agent implements two non-negotiable runtime guardrails:

### 5.1 Internal Timeout Management
* **Risk:** The marketplace disconnects if a request exceeds `timeout_seconds`, registering a task failure.
* **Mechanism:** The agent computes a defensive internal timeout:
  $$\text{effective\_timeout} = \max\left(1.0, \text{timeout\_seconds} - \text{INTERNAL\_TIMEOUT\_SAFETY\_BUFFER\_SECONDS}\right)$$
* **Implementation:** The service wraps the LLM request in `asyncio.wait_for(..., timeout=effective_timeout)`.
* **Timeout Handling:** If the timeout fires before the LLM concludes, the service catches `asyncio.TimeoutError` and immediately returns a graceful fallback completion or partial output rather than dropping the connection.

### 5.2 Strict Word-Count Enforcement & Calculation
* **Prompt Directive:** The system prompt explicitly instructs the LLM to complete its response within `max_words`.
* **Post-Processing Trimmer:** Because generative models can overshoot word budgets, a deterministic post-processor trims the response:
  1. Tokenize text into words using standard whitespace splitting (`words = output_text.split()`).
  2. If `len(words) > max_words`, slice `words[:max_words]` and locate the last sentence terminator (`.`, `!`, `?`).
  3. If no terminator is found nearby, truncate cleanly at `max_words` and append an ellipsis.
* **Accurate Word Count:** `word_count` in the response is computed strictly as `len(output_text.split())` after post-processing, guaranteeing `word_count <= max_words`.

---

## 6. Immediate Implementation Steps for Generalist Agent

1. **Environment & Dependency Setup:**
   * Create `requirements.txt` with `fastapi`, `uvicorn[standard]`, `pydantic`, `pydantic-settings`, `openai`, `python-dotenv`.
2. **Scaffold Directory Structure:**
   * Establish `agents/generalist/` with its `.env.example`, `config.py`, `schemas.py`, `prompts.py`, `service.py`, and `router.py`.
3. **Implement Generalist Service Logic:**
   * Define prompt templates tailored for all-around analysis, drafting, and synthesis.
   * Implement `AsyncOpenAI` client wrapper with dynamic `effective_timeout` and sentence-aware word trimming.
4. **Implement Router & Fast-Path Health Check:**
   * Construct `agents/generalist/router.py` with `POST /webhook` and `GET /health`.
5. **Implement Main Gateway Server:**
   * Author `main.py` mounting `agents.generalist.router.router` under the `/generalist` prefix.
6. **Local Verification:**
   * Validate using simulated curl requests matching the Marketplace Webhook specification.
   * Verify timeout guardrail and word count limits under boundary conditions.
7. **Kavver Integration:**
   * Connect to the Kavver runner to verify webhook dispatch and registration.
