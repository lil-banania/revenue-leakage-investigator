"""Tier 2 investigator atomic tools (read-only)."""
from __future__ import annotations

from typing import Any, Dict, List, Literal

from pydantic import BaseModel, ConfigDict, Field

from config import get_billing_source
from .tools import PERIOD_CLOSE


class QueryRawEventsInput(BaseModel):
    model_config = ConfigDict(extra="forbid")

    account_id: str = Field(min_length=1)
    period: str = Field(pattern=r"^\d{4}-\d{2}$")
    event_type: Literal["all", "late", "duplicate"] = "all"


class QueryRawEventsOutput(BaseModel):
    model_config = ConfigDict(extra="forbid")

    account_id: str
    period: str
    event_type: str
    event_count: int
    unique_event_count: int
    total_quantity: int
    late_event_count: int
    duplicate_event_count: int
    sample_event_ids: List[str] = Field(default_factory=list)


class GetInvoiceLinesInput(BaseModel):
    model_config = ConfigDict(extra="forbid")

    account_id: str = Field(min_length=1)
    period: str = Field(pattern=r"^\d{4}-\d{2}$")


class GetInvoiceLinesOutput(BaseModel):
    model_config = ConfigDict(extra="forbid")

    account_id: str
    period: str
    line_items: List[Dict[str, Any]]


class GetCustomPricingRulesInput(BaseModel):
    model_config = ConfigDict(extra="forbid")

    account_id: str = Field(min_length=1)
    query: str = Field(default="pricing override")


class GetCustomPricingRulesOutput(BaseModel):
    model_config = ConfigDict(extra="forbid")

    account_id: str
    matched_rules: List[Dict[str, Any]]
    retrieved_count: int


class CompareAmountsInput(BaseModel):
    model_config = ConfigDict(extra="forbid")

    a: float
    b: float


class CompareAmountsOutput(BaseModel):
    model_config = ConfigDict(extra="forbid")

    a: float
    b: float
    delta: float
    direction: Literal["a_gt_b", "a_lt_b", "equal"]


def query_raw_events(account_id: str, period: str, event_type: str = "all") -> Dict[str, Any]:
    args = QueryRawEventsInput(account_id=account_id, period=period, event_type=event_type)
    source = get_billing_source()
    events = source.get_events(args.account_id, args.period)

    event_dicts = [
        {
            "event_id": e.event_id,
            "quantity": e.quantity,
            "timestamp": e.timestamp,
            "idempotency_key": e.idempotency_key,
        }
        for e in events
    ]
    seen_keys = set()
    duplicate_ids = []
    for e in event_dicts:
        key = e["idempotency_key"]
        if key in seen_keys:
            duplicate_ids.append(e["event_id"])
        seen_keys.add(key)
    late_ids = [e["event_id"] for e in event_dicts if e["timestamp"] >= PERIOD_CLOSE]

    if args.event_type == "late":
        filtered = [e for e in event_dicts if e["event_id"] in set(late_ids)]
    elif args.event_type == "duplicate":
        filtered = [e for e in event_dicts if e["event_id"] in set(duplicate_ids)]
    else:
        filtered = event_dicts

    out = QueryRawEventsOutput(
        account_id=args.account_id,
        period=args.period,
        event_type=args.event_type,
        event_count=len(filtered),
        unique_event_count=len({e["event_id"] for e in filtered}),
        total_quantity=sum(int(e["quantity"]) for e in filtered),
        late_event_count=len(late_ids),
        duplicate_event_count=len(duplicate_ids),
        sample_event_ids=[e["event_id"] for e in filtered[:8]],
    )
    return out.model_dump()


def get_invoice_lines(account_id: str, period: str) -> Dict[str, Any]:
    args = GetInvoiceLinesInput(account_id=account_id, period=period)
    source = get_billing_source()
    invoices = source.get_invoices(args.account_id, args.period)
    line_items: List[Dict[str, Any]] = []
    for inv in invoices:
        usage_component = round(float(inv.invoiced_amount) - float(inv.subscription_amount), 2)
        line_items.append(
            {
                "product_code": inv.product_code,
                "invoiced_quantity": inv.invoiced_quantity,
                "subscription_amount": float(inv.subscription_amount),
                "usage_amount": usage_component,
                "total_invoiced_amount": float(inv.invoiced_amount),
            }
        )
    out = GetInvoiceLinesOutput(account_id=args.account_id, period=args.period, line_items=line_items)
    return out.model_dump()


def get_custom_pricing_rules(account_id: str, query: str = "pricing override") -> Dict[str, Any]:
    args = GetCustomPricingRulesInput(account_id=account_id, query=query)
    source = get_billing_source()
    docs = source.get_contract_documents(args.account_id)

    query_tokens = {t.lower() for t in args.query.split() if t.strip()}
    ranked: List[tuple[int, Dict[str, Any]]] = []
    for doc in docs:
        body = doc.body.lower()
        score = sum(1 for t in query_tokens if t in body) + (2 if "override" in body else 0)
        ranked.append(
            (
                score,
                {
                    "document_id": doc.document_id,
                    "title": doc.title,
                    "content_type": doc.content_type,
                    "snippet": doc.body[:280],
                    "score": score,
                },
            )
        )
    ranked.sort(key=lambda item: item[0], reverse=True)
    matched = [row for _, row in ranked if row["score"] > 0]
    out = GetCustomPricingRulesOutput(
        account_id=args.account_id,
        matched_rules=matched[:5],
        retrieved_count=len(matched),
    )
    return out.model_dump()


def compare_amounts(a: float, b: float) -> Dict[str, Any]:
    args = CompareAmountsInput(a=a, b=b)
    delta = round(args.a - args.b, 2)
    if delta > 0:
        direction: Literal["a_gt_b", "a_lt_b", "equal"] = "a_gt_b"
    elif delta < 0:
        direction = "a_lt_b"
    else:
        direction = "equal"
    out = CompareAmountsOutput(a=args.a, b=args.b, delta=delta, direction=direction)
    return out.model_dump()
