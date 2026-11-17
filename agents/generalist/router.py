from functools import lru_cache
import logging
from fastapi import APIRouter, Depends
from agents.generalist.schemas import HealthResponse, WebhookRequest, WebhookResponse
from agents.generalist.service import GeneralistService

logger = logging.getLogger("generalist.router")

router = APIRouter(prefix="/generalist", tags=["generalist"])


@lru_cache
def get_service() -> GeneralistService:
    return GeneralistService()


@router.get("/health", response_model=HealthResponse)
async def health() -> HealthResponse:
    """Generalist agent health check probe."""
    return HealthResponse(status="ok", agent="generalist")


@router.post("", response_model=WebhookResponse)
@router.post("/webhook", response_model=WebhookResponse)
async def webhook(
    request: WebhookRequest,
    service: GeneralistService = Depends(get_service),
) -> WebhookResponse:
    """Process inbound webhook according to marketplace contract."""
    return await service.process_webhook(request)
