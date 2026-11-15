"""Monthly report: per office in local currency, combined in NOK."""
from __future__ import annotations
from datetime import datetime
from decimal import Decimal
from typing import List

from models import Currency, Office, Purchase, policy_of


class ReportBuilder:
    def __init__(self, purchases: List[Purchase]) -> None:
        self.purchases = purchases

    def build(self, month: datetime) -> str:
        def in_month(p: Purchase) -> bool:
            return p.date.year == month.year and p.date.month == month.month

        lines = [f"Snack spending, {month:%B %Y}"]
        combined_nok = Decimal(0)
        for office in Office:
            rows = [p for p in self.purchases if p.office == office and in_month(p)]
            total = sum((p.amount for p in rows), Decimal(0))
            pol = policy_of(office)
            budget = pol.monthly_budget
            lines.append(f"  {office.value}: {total} {pol.currency.value} "
                         f"(budget {budget}, used {total / budget:.0%})")
            combined_nok += total * pol.to_nok_rate
        lines.append(f"  Combined:  {combined_nok} NOK")
        return "\n".join(lines)
