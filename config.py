"""Runtime configuration for selecting the billing data source."""
from __future__ import annotations

import os

from src.sources.base import BillingSource
from src.sources.vynt_api import VyntApiSource
from src.sources.vynt_sim import VyntSimulatorSource


def get_billing_source() -> BillingSource:
    source_kind = os.getenv("BILLING_SOURCE", "sim").strip().lower()
    if source_kind == "sim":
        seed = int(os.getenv("SIM_SEED", "42"))
        return VyntSimulatorSource(seed=seed)
    if source_kind == "api":
        return VyntApiSource()
    raise ValueError(
        f"Unsupported BILLING_SOURCE='{source_kind}'. Use 'sim' or 'api'."
    )
