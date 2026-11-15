"""Tests proving the important rules. Run: python3 test_snacks.py"""
import sys
from datetime import datetime, timedelta
from decimal import Decimal

from adapters import SimulatedChatClient, SimulatedHRClient
from models import CommitmentStatus, Office, RefillState, Volunteer
from report import ReportBuilder
from service import SnackService

DAY1 = datetime(2026, 11, 2, 10, 0, 0)


class TestClock:
    def __init__(self, start):
        self._now = start

    def __call__(self):
        return self._now

    def advance_hours(self, h):
        self._now += timedelta(hours=h)

    def advance_days(self, d):
        self._now += timedelta(days=d)


def make_service(clock=None):
    oslo_a = Volunteer("Oslo-A", Office.OSLO)
    oslo_b = Volunteer("Oslo-B", Office.OSLO)
    blr_a = Volunteer("Blr-A", Office.BENGALURU)
    chat, hr = SimulatedChatClient(), SimulatedHRClient()
    svc = SnackService([oslo_a, oslo_b, blr_a], chat, hr, clock)
    return svc, chat, hr, oslo_a, oslo_b, blr_a


def open_and_assign(svc, office):
    request = svc.open_refill(office)
    commitment = next(c for c in svc.commitments if c.request_id == request.id)
    return request, commitment


# 1. Two volunteers cannot both commit to the same refill.
def test_only_one_commitment():
    svc, *_ = make_service()
    request, _ = open_and_assign(svc, Office.OSLO)
    active = [c for c in svc.commitments if c.request_id == request.id]
    assert len(active) == 1, "expected exactly one active commitment"
    assert request.state == RefillState.ASSIGNED


# 2. A refill nobody completes is handed to someone else.
def test_expired_reassigned():
    clock = TestClock(DAY1)
    svc, _, _, oslo_a, oslo_b, _ = make_service(clock)
    request = svc.open_refill(Office.OSLO)
    first = next(c for c in svc.commitments if c.request_id == request.id)
    assert first.volunteer_id == oslo_a.id

    clock.advance_hours(25)  # past the 24h deadline
    assert svc.reassign_expired() is True, "expected reassignment"
    assert first.status == CommitmentStatus.EXPIRED
    second = max((c for c in svc.commitments if c.request_id == request.id),
                 key=lambda c: c.deadline)
    assert second.volunteer_id == oslo_b.id, "different volunteer should be picked"


# 3. Budget check happens before anyone spends, and blocks.
def test_budget_check_before_purchase():
    clock = TestClock(DAY1)
    svc, chat, *_ = make_service(clock)
    _, c1 = open_and_assign(svc, Office.BENGALURU)
    svc.accept(c1.id, Decimal(1000))
    svc.complete_purchase(c1.id, Decimal(14000), ["mixed box"])

    # Same month, 1000 INR left of 15000.
    svc.open_refill(Office.BENGALURU)
    c2 = next(c for c in svc.commitments if c.status == CommitmentStatus.PROPOSED)
    decision, remaining = svc.accept(c2.id, Decimal(3000))
    assert decision == "would_exceed"
    assert remaining == Decimal(1000)
    assert c2.status == CommitmentStatus.PROPOSED, "must NOT be approved"
    assert any("exceed the monthly budget" in m for m in chat.messages)


# 4. Manager override still lets a claim through.
def test_manager_override():
    clock = TestClock(DAY1)
    svc, _, hr, *_ = make_service(clock)
    _, c1 = open_and_assign(svc, Office.BENGALURU)
    svc.accept(c1.id, Decimal(1000))
    svc.complete_purchase(c1.id, Decimal(14500), ["mixed box"])

    svc.open_refill(Office.BENGALURU)
    c2 = next(c for c in svc.commitments if c.status == CommitmentStatus.PROPOSED)
    decision, _ = svc.accept(c2.id, Decimal(2000))
    assert decision == "would_exceed"

    svc.override_budget(c2.id, Decimal(2000))  # manager says yes
    svc.complete_purchase(c2.id, Decimal(2000), ["mixed box"])
    assert len(hr.claims) == 2


# 5. Over-estimate receipt: claim actual, flag for HR, ledger records actual.
def test_over_estimate_rule():
    svc, _, hr, *_ = make_service()
    _, c = open_and_assign(svc, Office.OSLO)
    svc.accept(c.id, Decimal(500))
    purchase = svc.complete_purchase(c.id, Decimal(700), ["chips", "nuts"])  # 40% over
    assert purchase.over_estimate is True
    assert hr.claims[0]["amount"] == Decimal(700), "HR claim carries the actual amount"
    assert hr.claims[0]["flagged"] is True


# 6. Monthly totals correct across both currencies.
def test_cross_currency_totals():
    svc, *_ = make_service()
    _, c1 = open_and_assign(svc, Office.OSLO)
    svc.accept(c1.id, Decimal(1000))
    svc.complete_purchase(c1.id, Decimal(1200), ["mixed"])

    _, c2 = open_and_assign(svc, Office.BENGALURU)
    svc.accept(c2.id, Decimal(3000))
    svc.complete_purchase(c2.id, Decimal(3000), ["mixed"])

    report = ReportBuilder(svc.purchases).build(DAY1)
    assert "Oslo: 1200 NOK" in report
    assert "Bengaluru: 3000 INR" in report
    assert "Combined:  1530.00 NOK" in report, report  # 1200 + 3000*0.11


# 7. Fairness rotation: least-recent volunteer, holidays skipped.
def test_fairness_rotation():
    clock = TestClock(DAY1)
    svc, _, _, oslo_a, oslo_b, _ = make_service(clock)
    _, c1 = open_and_assign(svc, Office.OSLO)
    svc.accept(c1.id, Decimal(500))
    svc.complete_purchase(c1.id, Decimal(500), ["mixed"])
    assert c1.volunteer_id == oslo_a.id

    _, c2 = open_and_assign(svc, Office.OSLO)
    assert c2.volunteer_id == oslo_b.id, "fairness should rotate"

    oslo_b.holiday_until = DAY1 + timedelta(days=3)
    _, c3 = open_and_assign(svc, Office.OSLO)
    assert c3.volunteer_id == oslo_a.id, "holiday volunteer must be skipped"


if __name__ == "__main__":
    tests = [v for k, v in sorted(globals().items()) if k.startswith("test_")]
    failed = 0
    for t in tests:
        try:
            t()
            print(f"PASS {t.__name__}")
        except AssertionError as e:
            failed += 1
            print(f"FAIL {t.__name__}: {e}")
    print(f"\n{len(tests) - failed}/{len(tests)} passed")
    sys.exit(1 if failed else 0)
