"""Future production connector for Vynt billing API/DB."""
from __future__ import annotations

from typing import List

from .base import Account, BillingSource, Invoice, UsageEvent


class VyntApiSource(BillingSource):
    """Placeholder for a real Vynt integration.

    The implementation is intentionally absent in this step.
    """

    def _not_implemented(self) -> NotImplementedError:
        return NotImplementedError(
            "BILLING_SOURCE=api selected, but VyntApiSource is not implemented yet. "
            "Switch to BILLING_SOURCE=sim for local/demo runs."
        )

    def list_accounts(self, period: str) -> List[Account]:
        raise self._not_implemented()

    def get_events(self, account_id: str, period: str) -> List[UsageEvent]:
        raise self._not_implemented()

    def get_invoices(self, account_id: str, period: str) -> List[Invoice]:
        raise self._not_implemented()
