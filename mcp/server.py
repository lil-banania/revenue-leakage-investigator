"""MCP stdio server exposing read-only reconciliation tools.

Design decision: tools are strictly read-only. In the worst case, the assistant can
produce an incorrect report, but it can never trigger an irreversible billing action.
"""
from __future__ import annotations

import json
import re
import sys
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from config import get_billing_source
from src import tools as recon_tools

SERVER_INFO = {"name": "revenue-leakage-mcp", "version": "0.1.0"}
PERIOD_RE = re.compile(r"^\d{4}-\d{2}$")
ACCOUNT_RE = re.compile(r"^acct_\d{3}$")
PERIOD_CLOSE = datetime(2026, 6, 1)


def _ok(request_id: Any, result: Dict[str, Any]) -> Dict[str, Any]:
    return {"jsonrpc": "2.0", "id": request_id, "result": result}


def _err(request_id: Any, code: int, message: str) -> Dict[str, Any]:
    return {"jsonrpc": "2.0", "id": request_id, "error": {"code": code, "message": message}}


def _validate_period(value: Any) -> str:
    if not isinstance(value, str) or not PERIOD_RE.match(value):
        raise ValueError("`period` must be a string in YYYY-MM format.")
    return value


def _validate_account_id(value: Any) -> str:
    if not isinstance(value, str) or not ACCOUNT_RE.match(value):
        raise ValueError("`account_id` must match pattern acct_XXX.")
    return value


def _validate_quantity(value: Any) -> int:
    if not isinstance(value, int):
        raise ValueError("`quantity` must be an integer.")
    if value < 0 or value > 100_000_000:
        raise ValueError("`quantity` must be in range [0, 100000000].")
    return value


def _tool_specs() -> List[Dict[str, Any]]:
    return [
        {
            "name": "list_accounts",
            "description": "List available customer accounts for a billing period.",
            "inputSchema": {
                "type": "object",
                "properties": {"period": {"type": "string", "pattern": r"^\d{4}-\d{2}$"}},
                "required": ["period"],
                "additionalProperties": False,
            },
        },
        {
            "name": "dedup_events",
            "description": "Return account events after idempotency-based de-duplication.",
            "inputSchema": {
                "type": "object",
                "properties": {
                    "period": {"type": "string", "pattern": r"^\d{4}-\d{2}$"},
                    "account_id": {"type": "string", "pattern": r"^acct_\d{3}$"},
                },
                "required": ["period", "account_id"],
                "additionalProperties": False,
            },
        },
        {
            "name": "include_late_events",
            "description": "Show events that occurred after period close (late usage).",
            "inputSchema": {
                "type": "object",
                "properties": {
                    "period": {"type": "string", "pattern": r"^\d{4}-\d{2}$"},
                    "account_id": {"type": "string", "pattern": r"^acct_\d{3}$"},
                },
                "required": ["period", "account_id"],
                "additionalProperties": False,
            },
        },
        {
            "name": "recompute_tier_price",
            "description": "Recompute deterministic usage charge for a given quantity.",
            "inputSchema": {
                "type": "object",
                "properties": {
                    "quantity": {"type": "integer", "minimum": 0, "maximum": 100000000}
                },
                "required": ["quantity"],
                "additionalProperties": False,
            },
        },
        {
            "name": "reconcile_account",
            "description": "Run deterministic account-level reconciliation and return finding.",
            "inputSchema": {
                "type": "object",
                "properties": {
                    "period": {"type": "string", "pattern": r"^\d{4}-\d{2}$"},
                    "account_id": {"type": "string", "pattern": r"^acct_\d{3}$"},
                },
                "required": ["period", "account_id"],
                "additionalProperties": False,
            },
        },
    ]


def _load_account_context(period: str, account_id: str) -> tuple[list[dict], dict]:
    source = get_billing_source()
    events = source.get_events(account_id, period)
    invoices = source.get_invoices(account_id, period)
    if not invoices:
        raise ValueError(f"No invoice found for {account_id} in {period}.")
    invoice = invoices[0]
    event_dicts = [
        {
            "event_id": e.event_id,
            "account_id": e.account_id,
            "product_code": e.product_code,
            "quantity": str(e.quantity),
            "timestamp": e.timestamp.isoformat(),
            "idempotency_key": e.idempotency_key,
        }
        for e in events
    ]
    invoice_dict = {
        "account_id": invoice.account_id,
        "product_code": invoice.product_code,
        "period": invoice.period,
        "invoiced_quantity": str(invoice.invoiced_quantity),
        "invoiced_amount": str(invoice.invoiced_amount),
        "subscription_amount": str(invoice.subscription_amount),
    }
    return event_dicts, invoice_dict


def _call_tool(name: str, args: Dict[str, Any]) -> Dict[str, Any]:
    if name == "list_accounts":
        period = _validate_period(args.get("period"))
        source = get_billing_source()
        accounts = source.list_accounts(period)
        return {
            "period": period,
            "count": len(accounts),
            "accounts": [a.model_dump() for a in accounts],
        }

    if name == "dedup_events":
        period = _validate_period(args.get("period"))
        account_id = _validate_account_id(args.get("account_id"))
        events, _ = _load_account_context(period, account_id)
        deduped = recon_tools.dedup_events(events)
        return {
            "period": period,
            "account_id": account_id,
            "raw_events": len(events),
            "deduped_events": len(deduped),
            "removed_duplicates": len(events) - len(deduped),
        }

    if name == "include_late_events":
        period = _validate_period(args.get("period"))
        account_id = _validate_account_id(args.get("account_id"))
        events, _ = _load_account_context(period, account_id)
        late = [e for e in events if datetime.fromisoformat(e["timestamp"]) >= PERIOD_CLOSE]
        deduped = recon_tools.dedup_events(events)
        qty_total = sum(int(e["quantity"]) for e in deduped)
        return {
            "period": period,
            "account_id": account_id,
            "late_event_count": len(late),
            "correct_billable_qty_with_late": qty_total,
        }

    if name == "recompute_tier_price":
        quantity = _validate_quantity(args.get("quantity"))
        amount = recon_tools.tier_price_total(quantity)
        return {"quantity": quantity, "usage_amount": amount}

    if name == "reconcile_account":
        period = _validate_period(args.get("period"))
        account_id = _validate_account_id(args.get("account_id"))
        events, invoice = _load_account_context(period, account_id)
        finding = recon_tools.reconcile_account(account_id, events, invoice)
        return {
            "period": period,
            "account_id": account_id,
            "finding": finding,
            "status": "flagged" if finding else "clean",
        }

    raise ValueError(f"Unknown tool '{name}'.")


def _handle(request: Dict[str, Any]) -> Dict[str, Any]:
    request_id = request.get("id")
    method = request.get("method")
    params = request.get("params", {})

    try:
        if method == "initialize":
            return _ok(
                request_id,
                {
                    "protocolVersion": "2024-11-05",
                    "serverInfo": SERVER_INFO,
                    "capabilities": {"tools": {}},
                },
            )
        if method == "notifications/initialized":
            return {}
        if method == "tools/list":
            return _ok(request_id, {"tools": _tool_specs()})
        if method == "tools/call":
            name = params.get("name")
            if not isinstance(name, str):
                raise ValueError("tools/call requires a string `name`.")
            arguments = params.get("arguments", {})
            if not isinstance(arguments, dict):
                raise ValueError("tools/call requires object `arguments`.")
            payload = _call_tool(name, arguments)
            return _ok(
                request_id,
                {
                    "content": [{"type": "text", "text": json.dumps(payload, ensure_ascii=True)}],
                    "structuredContent": payload,
                    "isError": False,
                },
            )
        return _err(request_id, -32601, f"Method not found: {method}")
    except NotImplementedError as exc:
        return _err(request_id, -32001, str(exc))
    except ValueError as exc:
        return _err(request_id, -32602, str(exc))
    except Exception as exc:  # defensive boundary
        return _err(request_id, -32000, f"Internal error: {exc}")


def main() -> None:
    for raw in sys.stdin:
        raw = raw.strip()
        if not raw:
            continue
        try:
            req = json.loads(raw)
            resp = _handle(req)
            if resp:
                sys.stdout.write(json.dumps(resp, ensure_ascii=True) + "\n")
                sys.stdout.flush()
        except json.JSONDecodeError:
            sys.stdout.write(
                json.dumps(_err(None, -32700, "Parse error: expected JSON object."), ensure_ascii=True) + "\n"
            )
            sys.stdout.flush()


if __name__ == "__main__":
    main()
