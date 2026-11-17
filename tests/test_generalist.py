import asyncio
from unittest.mock import AsyncMock, MagicMock
from httpx import ASGITransport, AsyncClient
import pytest

from agents.generalist.config import GeneralistSettings
from agents.generalist.main import app as standalone_app
from agents.generalist.router import get_service
from agents.generalist.schemas import WebhookRequest, WebhookResponse
from agents.generalist.service import GeneralistService, trim_to_word_limit
from main import app


# ---------------------------------------------------------------------------
# Unit tests for trim_to_word_limit
# ---------------------------------------------------------------------------


def test_trim_to_word_limit_under_limit():
    text = "This is a short sentence."
    trimmed, count = trim_to_word_limit(text, 10)
    assert trimmed == "This is a short sentence."
    assert count == 5


def test_trim_to_word_limit_exact_limit():
    text = "One two three four five."
    trimmed, count = trim_to_word_limit(text, 5)
    assert trimmed == "One two three four five."
    assert count == 5


def test_trim_to_word_limit_sentence_boundary_within_last_20_percent():
    # 10 words total, last sentence ends at word 9 (index 8/9).
    text = "Alpha beta gamma delta epsilon zeta eta theta iota. Kappa."
    # max_words = 10 -> candidate has 10 words. Terminator '.' is right at the 9th word.
    trimmed, count = trim_to_word_limit(text, 9)
    assert trimmed.endswith(".")
    assert count <= 9


def test_trim_to_word_limit_ellipsis_when_no_terminator():
    # Words without terminators
    text = "word one two three four five six seven eight nine ten eleven"
    trimmed, count = trim_to_word_limit(text, 5)
    assert trimmed.endswith("...")
    assert count <= 5


def test_trim_to_word_limit_empty():
    trimmed, count = trim_to_word_limit("", 10)
    assert trimmed == ""
    assert count == 0

    trimmed, count = trim_to_word_limit("   ", 10)
    assert trimmed == ""
    assert count == 0


def test_trim_to_word_limit_zero_or_negative():
    text = "Hello world"
    trimmed, count = trim_to_word_limit(text, 0)
    assert trimmed == ""
    assert count == 0

    trimmed, count = trim_to_word_limit(text, -5)
    assert trimmed == ""
    assert count == 0


# ---------------------------------------------------------------------------
# Service & DI unit tests
# ---------------------------------------------------------------------------


def test_get_service_singleton():
    service1 = get_service()
    service2 = get_service()
    assert isinstance(service1, GeneralistService)
    assert service1 is service2
    assert service1.client is not None


# ---------------------------------------------------------------------------
# Gateway integration tests
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_root_endpoint():
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        resp = await client.get("/")
        assert resp.status_code == 200
        data = resp.json()
        assert data.get("status") == "ok"
        assert data.get("service") == "agent-gateway"
        assert data.get("version") == "1.0.0"


@pytest.mark.asyncio
async def test_root_health():
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        resp = await client.get("/health")
        assert resp.status_code == 200
        assert resp.json() == {"status": "ok", "service": "agent-gateway"}


@pytest.mark.asyncio
async def test_generalist_health():
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        resp = await client.get("/generalist/health")
        assert resp.status_code == 200
        assert resp.json() == {"status": "ok", "agent": "generalist"}


@pytest.mark.asyncio
async def test_webhook_valid_request():
    mock_llm_client = MagicMock()
    mock_choice = MagicMock()
    mock_choice.message.content = "Here is a high quality response to your query."
    mock_response = MagicMock(choices=[mock_choice])
    mock_llm_client.chat.completions.create = AsyncMock(return_value=mock_response)

    settings = GeneralistSettings(model_tag="test-generalist-tag")
    test_service = GeneralistService(settings=settings, client=mock_llm_client)

    app.dependency_overrides[get_service] = lambda: test_service
    try:
        payload = {
            "id": "req-123",
            "match_id": "match-456",
            "type": "general_qa",
            "category": "science",
            "prompt": "Explain quantum computing briefly.",
            "max_words": 50,
            "timeout_seconds": 10.0,
        }
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            resp = await client.post("/generalist/webhook", json=payload)
            assert resp.status_code == 200
            data = resp.json()
            # Must strictly match marketplace schema: only output_text
            assert list(data.keys()) == ["output_text"]
            assert data["output_text"] == "Here is a high quality response to your query."
            assert len(data["output_text"].split()) <= 50
    finally:
        app.dependency_overrides.clear()


@pytest.mark.asyncio
async def test_webhook_word_count_overflow():
    long_response = (
        "Artificial intelligence is rapidly advancing across multiple disciplines including "
        "medicine education engineering and finance with widespread adoption across the world today."
    )
    mock_llm_client = MagicMock()
    mock_choice = MagicMock()
    mock_choice.message.content = long_response
    mock_response = MagicMock(choices=[mock_choice])
    mock_llm_client.chat.completions.create = AsyncMock(return_value=mock_response)

    settings = GeneralistSettings(model_tag="test-generalist-tag")
    test_service = GeneralistService(settings=settings, client=mock_llm_client)

    app.dependency_overrides[get_service] = lambda: test_service
    try:
        payload = {
            "id": "req-124",
            "match_id": "match-789",
            "type": "general_qa",
            "category": "technology",
            "prompt": "Tell me about AI.",
            "max_words": 10,
            "timeout_seconds": 10.0,
        }
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            resp = await client.post("/generalist/webhook", json=payload)
            assert resp.status_code == 200
            data = resp.json()
            assert list(data.keys()) == ["output_text"]
            assert len(data["output_text"].split()) <= 10
    finally:
        app.dependency_overrides.clear()


@pytest.mark.asyncio
async def test_webhook_empty_response_fallback():
    mock_llm_client = MagicMock()
    mock_choice = MagicMock()
    mock_choice.message.content = "   "
    mock_response = MagicMock(choices=[mock_choice])
    mock_llm_client.chat.completions.create = AsyncMock(return_value=mock_response)

    settings = GeneralistSettings(model_tag="test-generalist-tag")
    test_service = GeneralistService(settings=settings, client=mock_llm_client)

    app.dependency_overrides[get_service] = lambda: test_service
    try:
        payload = {
            "id": "req-empty",
            "match_id": "match-empty-001",
            "type": "general_qa",
            "category": "general",
            "prompt": "Say nothing",
            "max_words": 10,
            "timeout_seconds": 5.0,
        }
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            resp = await client.post("/generalist/webhook", json=payload)
            assert resp.status_code == 200
            data = resp.json()
            assert list(data.keys()) == ["output_text"]
            assert len(data["output_text"]) > 0
            assert len(data["output_text"].split()) <= 10
    finally:
        app.dependency_overrides.clear()


@pytest.mark.asyncio
async def test_webhook_passes_max_tokens():
    mock_llm_client = MagicMock()
    mock_choice = MagicMock()
    mock_choice.message.content = "Short answer."
    mock_response = MagicMock(choices=[mock_choice])
    mock_llm_client.chat.completions.create = AsyncMock(return_value=mock_response)

    settings = GeneralistSettings(llm_max_tokens=500)
    test_service = GeneralistService(settings=settings, client=mock_llm_client)

    app.dependency_overrides[get_service] = lambda: test_service
    try:
        payload = {
            "id": "req-tokens",
            "match_id": "match-tokens-001",
            "type": "general_qa",
            "category": "general",
            "prompt": "Test tokens",
            "max_words": 10,
            "timeout_seconds": 5.0,
        }
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            resp = await client.post("/generalist/webhook", json=payload)
            assert resp.status_code == 200
            _, kwargs = mock_llm_client.chat.completions.create.call_args
            assert kwargs.get("max_tokens") == 64
    finally:
        app.dependency_overrides.clear()


@pytest.mark.asyncio
async def test_webhook_timeout_fallback():
    async def slow_completion(*args, **kwargs):
        await asyncio.sleep(5.0)
        return MagicMock()

    mock_llm_client = MagicMock()
    mock_llm_client.chat.completions.create = slow_completion

    settings = GeneralistSettings(
        model_tag="test-generalist-tag",
        internal_timeout_safety_buffer_seconds=2.0,
    )
    test_service = GeneralistService(settings=settings, client=mock_llm_client)

    app.dependency_overrides[get_service] = lambda: test_service
    try:
        payload = {
            "id": "req-timeout",
            "match_id": "match-timeout-001",
            "type": "general_qa",
            "category": "general",
            "prompt": "Test hanging prompt",
            "max_words": 20,
            "timeout_seconds": 1.0,
        }
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            resp = await client.post("/generalist/webhook", json=payload)
            assert resp.status_code == 200
            data = resp.json()
            assert list(data.keys()) == ["output_text"]
            assert "allocated time limit" in data["output_text"]
            assert len(data["output_text"].split()) <= 20
    finally:
        app.dependency_overrides.clear()


@pytest.mark.asyncio
async def test_webhook_llm_exception_fallback():
    mock_llm_client = MagicMock()
    mock_llm_client.chat.completions.create = AsyncMock(side_effect=RuntimeError("OpenAI API unreachable"))

    settings = GeneralistSettings(model_tag="test-generalist-tag")
    test_service = GeneralistService(settings=settings, client=mock_llm_client)

    app.dependency_overrides[get_service] = lambda: test_service
    try:
        payload = {
            "id": "req-err",
            "match_id": "match-err-002",
            "type": "general_qa",
            "category": "general",
            "prompt": "Test error handling",
            "max_words": 20,
            "timeout_seconds": 5.0,
        }
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            resp = await client.post("/generalist/webhook", json=payload)
            assert resp.status_code == 200
            data = resp.json()
            assert list(data.keys()) == ["output_text"]
            assert "error" in data["output_text"].lower()
            assert len(data["output_text"].split()) <= 20
    finally:
        app.dependency_overrides.clear()


@pytest.mark.asyncio
async def test_webhook_invalid_payload():
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        # Missing required fields
        resp = await client.post("/generalist/webhook", json={"id": "only-id"})
        assert resp.status_code == 422

        # Negative max_words
        resp = await client.post(
            "/generalist/webhook",
            json={
                "id": "1",
                "match_id": "m1",
                "type": "t",
                "category": "c",
                "prompt": "p",
                "max_words": -5,
                "timeout_seconds": 10.0,
            },
        )
        assert resp.status_code == 422

        # Negative timeout_seconds
        resp = await client.post(
            "/generalist/webhook",
            json={
                "id": "1",
                "match_id": "m1",
                "type": "t",
                "category": "c",
                "prompt": "p",
                "max_words": 10,
                "timeout_seconds": -1.0,
            },
        )
        assert resp.status_code == 422


@pytest.mark.asyncio
async def test_unhandled_route_exception():
    mock_service = MagicMock()
    mock_service.process_webhook = AsyncMock(side_effect=RuntimeError("Database crash simulation"))

    app.dependency_overrides[get_service] = lambda: mock_service
    try:
        transport = ASGITransport(app=app, raise_app_exceptions=False)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            resp = await client.post(
                "/generalist/webhook",
                json={
                    "id": "1",
                    "match_id": "m1",
                    "type": "t",
                    "category": "c",
                    "prompt": "p",
                    "max_words": 10,
                    "timeout_seconds": 10.0,
                },
            )
            assert resp.status_code == 500
            assert resp.json() == {"detail": "Internal server error"}
    finally:
        app.dependency_overrides.clear()


# ---------------------------------------------------------------------------
# Standalone Agent Endpoint Tests (POST / matching marketplace contract)
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_standalone_marketplace_post_root():
    """Verify that standalone app accepts POST / with exact marketplace payload format."""
    mock_llm_client = MagicMock()
    mock_choice = MagicMock()
    mock_choice.message.content = "The pendulum swung with rhythmic precision inside the aged mahogany cabinet..."
    mock_response = MagicMock(choices=[mock_choice])
    mock_llm_client.chat.completions.create = AsyncMock(return_value=mock_response)

    test_service = GeneralistService(client=mock_llm_client)
    standalone_app.dependency_overrides[get_service] = lambda: test_service

    try:
        payload = {
            "id": "mat_qual_60592751ef9f4305_1",
            "match_id": "mat_qual_60592751ef9f4305_1",
            "type": "match:execute",
            "category": "creative-fiction/qualification",
            "prompt": "Write an exact 150-word story about an antique clock.",
            "max_words": 200,
            "timeout_seconds": 30,
        }
        transport = ASGITransport(app=standalone_app)
        async with AsyncClient(transport=transport, base_url="http://localhost:8000") as client:
            # Test POST /
            resp = await client.post("/", json=payload)
            assert resp.status_code == 200
            data = resp.json()
            assert list(data.keys()) == ["output_text"]
            assert data["output_text"].startswith("The pendulum swung")

            # Test POST /webhook alias
            resp_webhook = await client.post("/webhook", json=payload)
            assert resp_webhook.status_code == 200
            assert resp_webhook.json() == data

            # Test GET /health
            resp_health = await client.get("/health")
            assert resp_health.status_code == 200
            assert resp_health.json() == {"status": "ok", "agent": "generalist"}
    finally:
        standalone_app.dependency_overrides.clear()
