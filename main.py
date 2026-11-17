import logging
from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse

from agents.generalist.router import router as generalist_router

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger("gateway")

app = FastAPI(
    title="Unified AI Agent Gateway",
    description="Unified gateway server hosting isolated AI agent webhook endpoints.",
    version="1.0.0",
)

# Global exception handlers
@app.exception_handler(Exception)
async def generic_exception_handler(request: Request, exc: Exception) -> JSONResponse:
    logger.exception("Unhandled gateway exception on %s %s: %s", request.method, request.url.path, exc)
    return JSONResponse(
        status_code=500,
        content={"detail": "Internal server error"},
    )


@app.get("/health", tags=["system"])
async def root_health() -> dict[str, str]:
    """Root gateway health probe."""
    return {"status": "ok", "service": "agent-gateway"}


@app.get("/", tags=["system"])
async def root() -> dict[str, str]:
    """Root info endpoint."""
    return {"status": "ok", "service": "agent-gateway", "version": "1.0.0"}


# Mount isolated agent routers
app.include_router(generalist_router)


if __name__ == "__main__":
    import uvicorn

    uvicorn.run("main:app", host="0.0.0.0", port=8000, reload=True)
