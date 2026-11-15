"""Domain models. Pure data, no dependencies on infrastructure."""
from __future__ import annotations
from dataclasses import dataclass, field
from datetime import datetime
from decimal import Decimal
from enum import Enum
from typing import List, Optional
import uuid


class Office(Enum):
    OSLO = "Oslo"
    BENGALURU = "Bengaluru"


class Currency(Enum):
    NOK = "NOK"
    INR = "INR"


class RefillState(Enum):
    OPEN = "Open"
    ASSIGNED = "Assigned"
    AWAITING_RECEIPT = "AwaitingReceipt"
    CLAIMED = "Claimed"
    REIMBURSED = "Reimbursed"


class CommitmentStatus(Enum):
    PROPOSED = "Proposed"
    ACCEPTED = "Accepted"
    COMPLETED = "Completed"
    PASSED = "Passed"
    EXPIRED = "Expired"


def new_id() -> str:
    return str(uuid.uuid4())


@dataclass
class Volunteer:
    name: str
    home_office: Office
    id: str = field(default_factory=new_id)
    holiday_until: Optional[datetime] = None

    def is_available(self, now: datetime) -> bool:
        return self.holiday_until is None or now > self.holiday_until


@dataclass
class RefillRequest:
    office: Office
    opened_at: datetime
    id: str = field(default_factory=new_id)
    state: RefillState = RefillState.OPEN
    active_commitment_id: Optional[str] = None


@dataclass
class Commitment:
    request_id: str
    volunteer_id: str
    deadline: datetime
    currency: Currency
    id: str = field(default_factory=new_id)
    status: CommitmentStatus = CommitmentStatus.PROPOSED
    approved_estimate: Optional[Decimal] = None


@dataclass
class Purchase:
    office: Office
    amount: Decimal
    currency: Currency
    items: List[str]
    date: datetime
    volunteer_id: str
    claim_id: str
    over_estimate: bool
    id: str = field(default_factory=new_id)


class OfficePolicy:
    """Per-office settings: currency, budget, FX for the combined report.

    Extension point: a new office only needs a new policy, nothing else changes.
    """

    def __init__(self, currency: Currency, monthly_budget: Decimal, to_nok_rate: Decimal):
        self.currency = currency
        self.monthly_budget = monthly_budget
        self.to_nok_rate = to_nok_rate


OFFICE_POLICIES = {
    Office.OSLO: OfficePolicy(Currency.NOK, Decimal("6000"), Decimal("1")),
    Office.BENGALURU: OfficePolicy(Currency.INR, Decimal("15000"), Decimal("0.11")),
}


def policy_of(office: Office) -> OfficePolicy:
    return OFFICE_POLICIES[office]
