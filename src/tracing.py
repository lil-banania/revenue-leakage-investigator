"""Lightweight tracing for investigations with JSON export and optional Langfuse hook."""
from __future__ import annotations

import json
import os
import time
import uuid
from contextlib import contextmanager
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _safe_json_size(payload: Any) -> int:
    try:
        return len(json.dumps(payload, ensure_ascii=True))
    except Exception:
        return len(str(payload))


def _token_cost_simulation(inputs: Any, outputs: Any) -> Dict[str, int]:
    # Rough deterministic approximation to keep traces comparable offline.
    in_tokens = max(1, _safe_json_size(inputs) // 4)
    out_tokens = max(1, _safe_json_size(outputs) // 4)
    return {
        "input_tokens": in_tokens,
        "output_tokens": out_tokens,
        "total_tokens": in_tokens + out_tokens,
    }


@dataclass
class TraceSpan:
    span_id: str
    name: str
    kind: str
    started_at: str
    ended_at: Optional[str] = None
    latency_ms: Optional[int] = None
    inputs: Any = field(default_factory=dict)
    outputs: Any = field(default_factory=dict)
    token_cost: Dict[str, int] = field(default_factory=dict)


class TraceRecorder:
    def __init__(self, period: str):
        self.trace_id = str(uuid.uuid4())
        self.period = period
        self.started_at = _utc_now()
        self.finished_at: Optional[str] = None
        self.spans: List[TraceSpan] = []
        self.trace_path: Optional[str] = None

    @contextmanager
    def span(self, name: str, kind: str, inputs: Any):
        span = TraceSpan(
            span_id=str(uuid.uuid4()),
            name=name,
            kind=kind,
            started_at=_utc_now(),
            inputs=inputs,
        )
        t0 = time.perf_counter()
        try:
            yield span
        finally:
            span.ended_at = _utc_now()
            span.latency_ms = int((time.perf_counter() - t0) * 1000)
            span.token_cost = _token_cost_simulation(span.inputs, span.outputs)
            self.spans.append(span)

    def finalize(self, final_state: Dict[str, Any]) -> str:
        self.finished_at = _utc_now()
        traces_dir = Path(os.getenv("TRACE_DIR", "traces"))
        traces_dir.mkdir(parents=True, exist_ok=True)
        out = traces_dir / f"{self.trace_id}.json"
        payload = {
            "trace_id": self.trace_id,
            "period": self.period,
            "started_at": self.started_at,
            "finished_at": self.finished_at,
            "summary": {
                "steps": final_state.get("steps", 0),
                "visited": final_state.get("visited", []),
                "finding_count": len(final_state.get("findings", [])),
                "total_leakage_usd": final_state.get("total_leakage_usd", 0.0),
            },
            "spans": [
                {
                    "span_id": s.span_id,
                    "name": s.name,
                    "kind": s.kind,
                    "started_at": s.started_at,
                    "ended_at": s.ended_at,
                    "latency_ms": s.latency_ms,
                    "inputs": s.inputs,
                    "outputs": s.outputs,
                    "token_cost": s.token_cost,
                }
                for s in self.spans
            ],
        }
        out.write_text(json.dumps(payload, indent=2, ensure_ascii=True), encoding="utf-8")
        self.trace_path = str(out)
        self._maybe_langfuse(payload)
        return self.trace_path

    def _maybe_langfuse(self, payload: Dict[str, Any]) -> None:
        if not (os.getenv("LANGFUSE_PUBLIC_KEY") and os.getenv("LANGFUSE_SECRET_KEY")):
            return
        try:
            from langfuse import Langfuse  # optional dependency; may be absent
        except Exception:
            return
        try:
            client = Langfuse(
                public_key=os.getenv("LANGFUSE_PUBLIC_KEY"),
                secret_key=os.getenv("LANGFUSE_SECRET_KEY"),
                host=os.getenv("LANGFUSE_HOST"),
            )
            trace = client.trace(
                name="revenue-leakage-investigation",
                id=payload["trace_id"],
                metadata={"period": payload["period"]},
            )
            for span in payload["spans"]:
                trace.span(
                    name=span["name"],
                    input=span["inputs"],
                    output=span["outputs"],
                    metadata={
                        "kind": span["kind"],
                        "latency_ms": span["latency_ms"],
                        "token_cost": span["token_cost"],
                    },
                )
            client.flush()
        except Exception:
            # Trace export must never fail investigation execution.
            return
