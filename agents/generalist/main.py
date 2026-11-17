import logging
from pathlib import Path
import sys

# Ensure agentics project root is on Python path
CURRENT_DIR = Path(__file__).resolve().parent
PROJECT_ROOT = CURRENT_DIR.parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from fastapi import Depends, FastAPI
from agents.generalist.config import get_settings
from agents.generalist.router import get_service, router as generalist_router
from agents.generalist.schemas import HealthResponse, WebhookRequest, WebhookResponse
from agents.generalist.service import GeneralistService

# Setup logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger("generalist.standalone")

settings = get_settings()

app = FastAPI(
    title="Generalist AI Agent Service",
    description="Standalone Generalist Agent Service conforming to marketplace contract",
    version="1.0.0",
)

# Root GET: information & liveness probe
@app.get("/")
async def root() -> dict[str, str]:
    return {
        "status": "ok",
        "agent": "generalist",
        "model": settings.llm_model_name,
        "endpoint": settings.effective_api_url,
    }


# Primary Marketplace Execution Endpoint: POST /
@app.post("/", response_model=WebhookResponse)
async def marketplace_execute_root(
    request: WebhookRequest,
    service: GeneralistService = Depends(get_service),
) -> WebhookResponse:
    """Primary marketplace incoming payload route: POST /"""
    return await service.process_webhook(request)


# Direct /webhook endpoint alias
@app.post("/webhook", response_model=WebhookResponse)
async def marketplace_execute_webhook(
    request: WebhookRequest,
    service: GeneralistService = Depends(get_service),
) -> WebhookResponse:
    """Direct webhook endpoint alias: POST /webhook"""
    return await service.process_webhook(request)


# Health check probe: GET /health
@app.get("/health", response_model=HealthResponse)
async def standalone_health() -> HealthResponse:
    """Standalone health check probe."""
    return HealthResponse(status="ok", agent="generalist")


# Also mount under /generalist for compatibility with gateway routing
app.include_router(generalist_router)


if __name__ == "__main__":
    import uvicorn

    print("=" * 60)
    print(f"  Starting Generalist AI Agent Standalone Service")
    print(f"  Port: {settings.port} | Host: {settings.agent_host}")
    print(f"  Model: {settings.llm_model_name}")
    print(f"  Target Endpoint: {settings.effective_api_url}")
    print(f"  Marketplace URL:  POST http://localhost:{settings.port}/")
    print(f"  Webhook URL:      POST http://localhost:{settings.port}/webhook")
    print(f"  Health URL:       GET  http://localhost:{settings.port}/health")
    print("=" * 60)

    uvicorn.run(
        app,
        host=settings.agent_host,
        port=settings.port,
        reload=False,
    )
