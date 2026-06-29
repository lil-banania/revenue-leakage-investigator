"""CLI helper to inspect an investigation trace step by step."""
from __future__ import annotations

import json
import sys
from pathlib import Path


def _latest_trace_path() -> Path:
    traces_dir = Path("traces")
    if not traces_dir.exists():
        raise FileNotFoundError("No traces/ directory found. Run an investigation first.")
    files = sorted(traces_dir.glob("*.json"), key=lambda p: p.stat().st_mtime, reverse=True)
    if not files:
        raise FileNotFoundError("No trace files found in traces/.")
    return files[0]


def main() -> None:
    trace_path = Path(sys.argv[1]) if len(sys.argv) > 1 else _latest_trace_path()
    payload = json.loads(trace_path.read_text(encoding="utf-8"))

    print(f"trace_file: {trace_path}")
    print(f"trace_id: {payload['trace_id']}")
    print(f"period: {payload['period']}")
    print(f"spans: {len(payload.get('spans', []))}")
    print("-" * 88)
    for idx, span in enumerate(payload.get("spans", []), start=1):
        tok = span.get("token_cost", {})
        print(
            f"{idx:02d}. {span['name']} [{span['kind']}] "
            f"latency={span.get('latency_ms', 0)}ms "
            f"tokens={tok.get('total_tokens', 0)}"
        )
        print(f"    inputs : {span.get('inputs', {})}")
        print(f"    outputs: {span.get('outputs', {})}")
    print("-" * 88)
    print(f"summary: {payload.get('summary', {})}")


if __name__ == "__main__":
    main()
