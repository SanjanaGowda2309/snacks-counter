"""SnackService: the refill lifecycle state machine.

Orchestrates the ports (chat, HR) and strategies (budget, rotation). All state
is injected or created here; nothing in this file knows about chat tools or HR
systems beyond the abstract interfaces.
"""
from __future__ import annotations
from datetime import datetime, timedelta
from decimal import Decimal
from typing import Callable, List, Optional

from adapters import ChatClient, HRClient
from models import (Commitment, CommitmentStatus, Currency, Office, Purchase,
                    RefillRequest, RefillState, Volunteer, new_id, policy_of)
from policies import BudgetPolicy, FairnessRotationPolicy, MonthlyBudgetPolicy, RotationPolicy


class SnackService:
    OVER_ESTIMATE_TOLERANCE = Decimal("0.10")
    ASSIGNMENT_TIMEOUT = timedelta(hours=24)

    def __init__(self, volunteers: List[Volunteer], chat: ChatClient, hr: HRClient,
                 clock: Optional[Callable[[], datetime]] = None,
                 budget_policy: Optional[BudgetPolicy] = None,
                 rotation_policy: Optional[RotationPolicy] = None) -> None:
        self.volunteers = volunteers
        self.chat = chat
        self.hr = hr
        self.clock = clock or (lambda: datetime.utcnow())
        self.budget_policy = budget_policy or MonthlyBudgetPolicy()
        self.rotation_policy = rotation_policy or FairnessRotationPolicy()
        self.requests: List[RefillRequest] = []
        self.commitments: List[Commitment] = []
        self.purchases: List[Purchase] = []

    # 1. OPEN
    def open_refill(self, office: Office) -> RefillRequest:
        request = RefillRequest(office=office, opened_at=self.clock())
        self.requests.append(request)
        self.chat.post_to_channel(office, "Snack box is empty. Opening a refill request.")
        self._assign(request)
        return request

    # 2. ASSIGN — at most one active commitment per request
    def _assign(self, request: RefillRequest, exclude: Optional[set] = None) -> None:
        volunteer = self.rotation_policy.pick_next(
            self.volunteers, request.office, self.clock(), self.purchases, exclude or set())
        if volunteer is None:
            raise RuntimeError("No available volunteer to assign.")
        commitment = Commitment(request_id=request.id, volunteer_id=volunteer.id,
                                deadline=self.clock() + self.ASSIGNMENT_TIMEOUT,
                                currency=policy_of(request.office).currency)
        self.commitments.append(commitment)
        request.active_commitment_id = commitment.id
        request.state = RefillState.ASSIGNED
        self.chat.direct_message(volunteer.id,
                                 "You've been picked for the next snack refill. Accept or pass?")

    def reassign_expired(self) -> bool:
        now = self.clock()
        for request in self.requests:
            if request.state != RefillState.ASSIGNED:
                continue
            c = self._get_commitment(request.active_commitment_id)
            if c.status == CommitmentStatus.PROPOSED and now > c.deadline:
                c.status = CommitmentStatus.EXPIRED
                self._assign(request, exclude={c.volunteer_id})
                return True
        return False

    def pass_commitment(self, commitment_id: str) -> None:
        c = self._get_commitment(commitment_id)
        request = self._get_request(c.request_id)
        if c.status != CommitmentStatus.PROPOSED:
            raise ValueError("Only a proposed commitment can be passed.")
        c.status = CommitmentStatus.PASSED
        request.active_commitment_id = None
        request.state = RefillState.OPEN
        self._assign(request, exclude={c.volunteer_id})

    # 3. ACCEPT + budget check BEFORE anyone spends
    def accept(self, commitment_id: str, estimate: Decimal) -> tuple[str, Decimal]:
        c = self._get_commitment(commitment_id)
        request = self._get_request(c.request_id)
        if request.active_commitment_id != c.id:
            raise ValueError("Commitment is not the active one for this request.")
        decision, remaining = self.budget_policy.check(
            request.office, self.clock(), estimate, self.purchases)
        if decision == BudgetPolicy.WITHIN_BUDGET:
            c.approved_estimate = estimate
            c.status = CommitmentStatus.ACCEPTED
            request.state = RefillState.AWAITING_RECEIPT
            self.chat.direct_message(c.volunteer_id,
                f"Approved up to {estimate} {c.currency.value}. If the receipt comes in "
                "higher, HR reviews it; you are guaranteed at least this amount.")
        else:
            self.chat.direct_message(c.volunteer_id,
                f"Estimate {estimate} {c.currency.value} would exceed the monthly budget "
                f"({remaining} {c.currency.value} left). Buy a smaller basket, wait for "
                "next month, or ask a manager to override.")
        return decision, remaining

    def override_budget(self, commitment_id: str, estimate: Decimal) -> None:
        """Manager override: approve an over-budget purchase explicitly."""
        c = self._get_commitment(commitment_id)
        request = self._get_request(c.request_id)
        c.approved_estimate = estimate
        c.status = CommitmentStatus.ACCEPTED
        request.state = RefillState.AWAITING_RECEIPT

    # 4-5. COMPLETE: record purchase, over-estimate rule, immediate HR claim
    def complete_purchase(self, commitment_id: str, actual_amount: Decimal,
                          items: List[str]) -> Purchase:
        c = self._get_commitment(commitment_id)
        request = self._get_request(c.request_id)
        if c.status != CommitmentStatus.ACCEPTED:
            raise ValueError("Purchase requires an accepted commitment.")
        over = actual_amount > c.approved_estimate * (1 + self.OVER_ESTIMATE_TOLERANCE)
        claim_id = self.hr.create_claim(actual_amount, c.currency,
                                        f"Snack refill, {request.office.value} ({', '.join(items)})",
                                        f"receipt-{c.id}", c.volunteer_id, over)
        purchase = Purchase(office=request.office, amount=actual_amount, currency=c.currency,
                            items=items, date=self.clock(), volunteer_id=c.volunteer_id,
                            claim_id=claim_id, over_estimate=over)
        self.purchases.append(purchase)
        c.status = CommitmentStatus.COMPLETED
        request.state = RefillState.CLAIMED
        self.chat.post_to_channel(request.office,
            f"Refill purchased for {actual_amount} {c.currency.value}. Claim submitted to HR.")
        return purchase

    def _get_commitment(self, commitment_id: str) -> Commitment:
        for c in self.commitments:
            if c.id == commitment_id:
                return c
        raise KeyError(f"Unknown commitment {commitment_id}")

    def _get_request(self, request_id: str) -> RefillRequest:
        for r in self.requests:
            if r.id == request_id:
                return r
        raise KeyError(f"Unknown request {request_id}")
