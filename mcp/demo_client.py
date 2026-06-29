"""Minimal stdio demo client for the local MCP reconciliation server."""
from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SERVER = ROOT / "mcp" / "server.py"


def _send(proc: subprocess.Popen[str], request: dict) -> dict:
    assert proc.stdin is not None
    assert proc.stdout is not None
    proc.stdin.write(json.dumps(request) + "\n")
    proc.stdin.flush()
    line = proc.stdout.readline()
    if not line:
        raise RuntimeError("No response from MCP server.")
    return json.loads(line)


def main() -> None:
    proc = subprocess.Popen(
        [sys.executable, str(SERVER)],
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
    )
    try:
        init = _send(
            proc,
            {"jsonrpc": "2.0", "id": 1, "method": "initialize", "params": {}},
        )
        print("initialize:", init.get("result", {}).get("serverInfo", {}))

        listing = _send(
            proc,
            {"jsonrpc": "2.0", "id": 2, "method": "tools/list", "params": {}},
        )
        print("tools:", [t["name"] for t in listing.get("result", {}).get("tools", [])])

        call = _send(
            proc,
            {
                "jsonrpc": "2.0",
                "id": 3,
                "method": "tools/call",
                "params": {
                    "name": "reconcile_account",
                    "arguments": {"period": "2026-05", "account_id": "acct_001"},
                },
            },
        )
        print("reconcile_account result:")
        print(json.dumps(call.get("result", {}).get("structuredContent", {}), indent=2))
    finally:
        proc.kill()


if __name__ == "__main__":
    main()
