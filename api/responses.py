from pydantic import BaseModel


class AckResponse(BaseModel):
    queued: bool
    message: str


class HealthResponse(BaseModel):
    status: str
    ready: bool
