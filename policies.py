"""Budget and rotation policies. Both are Strategy interfaces: swap policy
without touching SnackService."""
from __future__ import annotations
from abc import ABC, abstractmethod
from datetime import datetime, timedelta
from decimal import Decimal
from typing import List, Optional

from models import Office, Purchase, Volunteer, policy_of


class BudgetPolicy(ABC):
    """Decides whether an estimated spend is allowed right now."""

    WITHIN_BUDGET = "within_budget"
    WOULD_EXCEED = "would_exceed"

    @abstractmethod
    def check(self, office: Office, now: datetime, expected: Decimal,
              purchases: List[Purchase]) -> tuple[str, Decimal]:
        """Returns (decision, remaining_budget_in_office_currency)."""


class MonthlyBudgetPolicy(BudgetPolicy):
    def check(self, office, now, expected, purchases):
        spent = sum((p.amount for p in purchases
                     if p.office == office
                     and p.date.year == now.year and p.date.month == now.month),
                    Decimal(0))
        remaining = policy_of(office).monthly_budget - spent
        return (self.WITHIN_BUDGET if expected <= remaining else self.WOULD_EXCEED), remaining


class RotationPolicy(ABC):
    """Picks who buys next for an office."""

    @abstractmethod
    def pick_next(self, volunteers: List[Volunteer], office: Office, now: datetime,
                  purchases: List[Purchase], exclude: set) -> Optional[Volunteer]: ...


class FairnessRotationPolicy(RotationPolicy):
    """Fewest refills in the last 8 weeks wins; holidays skipped; roster order
    breaks ties deterministically."""

    FAIRNESS_WINDOW = timedelta(days=56)

    def pick_next(self, volunteers, office, now, purchases, exclude):
        eligible = [(i, v) for i, v in enumerate(volunteers)
                    if v.home_office == office and v.is_available(now)
                    and v.id not in exclude]
        if not eligible:
            return None
        return min(eligible, key=lambda iv: (
            sum(1 for p in purchases
                if p.volunteer_id == iv[1].id and now - p.date <= self.FAIRNESS_WINDOW),
            iv[0]))[1]
