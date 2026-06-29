# MCP Reconciliation Server

`mcp/server.py` exposes deterministic, read-only reconciliation tools over stdio.

## Safety

This server is intentionally read-only. It computes reports and diagnostics only.
No write path exists to mutate invoices, events, or external systems.

## Tools

- `list_accounts(period)`
- `dedup_events(period, account_id)`
- `include_late_events(period, account_id)`
- `recompute_tier_price(quantity)`
- `reconcile_account(period, account_id)`

All tools enforce strict JSON input schemas (types, regex patterns, and bounds).

## Run locally

```bash
python3 mcp/server.py
```

Each request/response is one JSON-RPC line on stdin/stdout.

## Demo client

```bash
python3 mcp/demo_client.py
```

This launches the server, calls `initialize`, `tools/list`, then `reconcile_account`.

## Claude Desktop config (example)

```json
{
  "mcpServers": {
    "revenue-leakage-investigator": {
      "command": "python3",
      "args": ["/ABSOLUTE/PATH/TO/revenue-leakage-investigator/mcp/server.py"]
    }
  }
}
```

Set `BILLING_SOURCE=sim` (default) for deterministic local runs.
