"""Ports (abstract interfaces) and in-memory adapters.

Ports & Adapters: the core service depends on these interfaces, never on the
concrete chat tool or HR system. Swapping in real integrations means writing a
new adapter, not touching the core.
"""
from __future__ import annotations
from abc import ABC, abstractmethod
from decimal import Decimal
from typing import List

from models import Currency, Office


class ChatClient(ABC):
    @abstractmethod
    def post_to_channel(self, office: Office, message: str) -> None: ...

    @abstractmethod
    def direct_message(self, volunteer_id: str, message: str) -> None: ...


class HRClient(ABC):
    @abstractmethod
    def create_claim(self, amount: Decimal, currency: Currency, description: str,
                     receipt_ref: str, employee_id: str, flagged: bool) -> str: ...


class SimulatedChatClient(ChatClient):
    """In-memory stand-in for the company's internal chat tool."""

    def __init__(self) -> None:
        self.messages: List[str] = []

    def post_to_channel(self, office: Office, message: str) -> None:
        self.messages.append(f"[{office.value} channel] {message}")

    def direct_message(self, volunteer_id: str, message: str) -> None:
        self.messages.append(f"[dm {volunteer_id[:8]}] {message}")


class SimulatedHRClient(HRClient):
    """In-memory stand-in for the third-party HR system."""

    def __init__(self) -> None:
        self.claims: List[dict] = []

    def create_claim(self, amount: Decimal, currency: Currency, description: str,
                     receipt_ref: str, employee_id: str, flagged: bool) -> str:
        from models import new_id
        claim_id = new_id()
        self.claims.append({"id": claim_id, "amount": amount, "currency": currency,
                            "description": description, "employee_id": employee_id,
                            "flagged": flagged})
        return claim_id
