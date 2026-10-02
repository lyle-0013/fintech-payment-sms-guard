from __future__ import annotations

from enum import Enum

from pydantic import BaseModel, ConfigDict, Field, field_validator


class PaymentEventKind(str, Enum):
    PAYMENT_POSTED = "payment_posted"
    PAYMENT_FAILED = "payment_failed"
    RISK_REVIEW = "risk_review"


class RiskLevel(str, Enum):
    LOW = "low"
    HIGH = "high"


class PaymentEventRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    event_id: str = Field(min_length=1, max_length=80)
    account_reference: str = Field(min_length=1, max_length=40)
    phone: str = Field(pattern=r"^\+[1-9]\d{7,14}$")
    kind: PaymentEventKind
    amount_minor: int = Field(ge=0)
    currency: str = Field(pattern=r"^[A-Z]{3}$")
    risk: RiskLevel = RiskLevel.LOW


class OptOutRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    phone: str = Field(pattern=r"^\+[1-9]\d{7,14}$")
    source: str = Field(min_length=1, max_length=60)


class NotificationResult(BaseModel):
    event_id: str
    audit_id: str
    decision: str
    reason: str
    message_id: str | None = None

    @field_validator("message_id")
    @classmethod
    def sent_has_message_id(cls, value: str | None, info):
        if info.data.get("decision") == "sent" and not value:
            raise ValueError("sent decisions require a message_id")
        return value
