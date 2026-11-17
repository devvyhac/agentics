from pydantic import BaseModel, Field


class WebhookRequest(BaseModel):
    id: str = Field(..., description="Unique request identifier")
    match_id: str = Field(..., description="Match or task identifier")
    type: str = Field(..., description="Task type descriptor, e.g. match:execute")
    category: str = Field(..., description="Task category, e.g. creative-fiction/qualification")
    prompt: str = Field(..., description="Inbound prompt text")
    max_words: int = Field(..., gt=0, description="Strict maximum words allowed in output")
    timeout_seconds: float = Field(..., gt=0, description="Available total execution timeout in seconds")


class WebhookResponse(BaseModel):
    output_text: str = Field(..., description="Generated text response matching marketplace schema")


class HealthResponse(BaseModel):
    status: str = "ok"
    agent: str = "generalist"
