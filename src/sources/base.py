"""Abstract billing source contract and typed DTOs."""
from __future__ import annotations

from abc import ABC, abstractmethod
from datetime import datetime
from typing import List

from pydantic import BaseModel, Field


class Account(BaseModel):
    account_id: str
    name: str
    plan: str


class UsageEvent(BaseModel):
    event_id: str
    account_id: str
    product_code: str
    quantity: int = Field(ge=0)
    timestamp: datetime
    idempotency_key: str


class Invoice(BaseModel):
    account_id: str
    product_code: str
    period: str
    invoiced_quantity: int = Field(ge=0)
    invoiced_amount: float = Field(ge=0.0)
    subscription_amount: float = Field(default=0.0, ge=0.0)


class ContractDocument(BaseModel):
    account_id: str
    document_id: str
    title: str
    content_type: str  # json | text
    body: str


class GroundTruthEntry(BaseModel):
    account_id: str
    issue: str
    root_cause: str


class BillingSource(ABC):
    """Source abstraction so agent logic is independent from data origin."""

    @abstractmethod
    def list_accounts(self, period: str) -> List[Account]:
        raise NotImplementedError

    @abstractmethod
    def get_events(self, account_id: str, period: str) -> List[UsageEvent]:
        raise NotImplementedError

    @abstractmethod
    def get_invoices(self, account_id: str, period: str) -> List[Invoice]:
        raise NotImplementedError

    # Optional extension points used by Tier 2 investigator.
    def get_contract_documents(self, account_id: str) -> List[ContractDocument]:
        raise NotImplementedError

    def get_ground_truth(self, period: str) -> List[GroundTruthEntry]:
        raise NotImplementedError
