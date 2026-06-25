from typing import Literal

from pydantic import BaseModel, Field


class MessageRequest(BaseModel):
    source: Literal["email", "contact_form", "ticket", "chat", "other"] = "other"
    customer_id: str = Field(min_length=1)
    message: str = Field(min_length=1)


class MessageResponse(BaseModel):
    trace_id: str
    intent: str
    confidence: float
    escalated: bool
    response: str


class BatchRequest(BaseModel):
    messages: list[MessageRequest]


class BatchResponse(BaseModel):
    results: list[MessageResponse]
