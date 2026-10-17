"""Pure, event-replayable shared Batch budget accounting; no I/O or inference.

The audited single-writer coordinator must retain and validate provider receipts,
persist each returned event *before* dispatch, and replay the same authorization
on resume. Constructing a receipt here does not authenticate it. Prices are an
explicit externally verified policy, never inferred from local tokenizers or a
model name. Amounts are integer nano-USD (1 USD = 10**9 units).

Admission reserves worst-case uncached/cache-write input and capped output. All
unknown outcomes remain reserved. Settlement is a conservative charge estimate,
not an invoice. A provider breach of the exact input/output contract freezes new
admission and records any observed excess truthfully; software cannot reverse
an already incurred provider charge. Taxes and unrelated account spending are
outside this authorization's API-usage ledger.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import datetime
from fractions import Fraction
import hashlib
import json
from typing import Any

NANOUSD_PER_USD = 1_000_000_000
MAX_CEILING_NANOUSD = 150 * NANOUSD_PER_USD
MAX_OPERATIONAL_NANOUSD = 140 * NANOUSD_PER_USD
METHOD = "event-batch-shared-budget-v1"


class BudgetError(ValueError):
    """A request, receipt or replay violates the frozen accounting contract."""


def _integer(value: Any, name: str, minimum: int = 0) -> int:
    if type(value) is not int or value < minimum:
        raise BudgetError("budget_invalid_" + name)
    return value


def _text(value: Any, name: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise BudgetError("budget_invalid_" + name)
    return value


def _sha(value: Any, name: str) -> str:
    if not isinstance(value, str) or len(value) != 64 or any(c not in "0123456789abcdef" for c in value):
        raise BudgetError("budget_invalid_" + name)
    return value


def _digest(value: Any) -> str:
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(",", ":"),
                                     ensure_ascii=False, allow_nan=False).encode()).hexdigest()


def _copy(value: Any) -> Any:
    return json.loads(json.dumps(value, allow_nan=False))


def _ratio(value: Any, name: str) -> Fraction:
    if not isinstance(value, (tuple, list)) or len(value) != 2:
        raise BudgetError("budget_invalid_" + name)
    return Fraction(_integer(value[0], name, 1), _integer(value[1], name, 1))


@dataclass(frozen=True)
class PricePolicy:
    """Explicit standard rates and applicable modifiers; all fields are required."""

    model: str
    input_nanousd_per_million: int
    cache_write_nanousd_per_million: int
    output_nanousd_per_million: int
    batch_multiplier: tuple[int, int]
    regional_multiplier: tuple[int, int]
    long_input_multiplier: tuple[int, int]
    long_output_multiplier: tuple[int, int]
    long_context_threshold: int
    source_url: str
    observed_at: str

    def __post_init__(self) -> None:
        _text(self.model, "model")
        for name in ("input_nanousd_per_million", "cache_write_nanousd_per_million",
                     "output_nanousd_per_million", "long_context_threshold"):
            _integer(getattr(self, name), name, 1)
        for name in ("batch_multiplier", "regional_multiplier", "long_input_multiplier", "long_output_multiplier"):
            ratio = _ratio(getattr(self, name), name)
            object.__setattr__(self, name, (ratio.numerator, ratio.denominator))
            if (name == "batch_multiplier" and ratio > 1) or (name != "batch_multiplier" and ratio < 1):
                raise BudgetError("budget_invalid_" + name)
        if not _text(self.source_url, "price_source").startswith("https://"):
            raise BudgetError("budget_invalid_price_source")
        try:
            instant = datetime.fromisoformat(self.observed_at.replace("Z", "+00:00"))
        except (AttributeError, TypeError, ValueError):
            raise BudgetError("budget_invalid_price_time") from None
        if instant.tzinfo is None:
            raise BudgetError("budget_invalid_price_time")

    @property
    def fingerprint(self) -> str:
        return _digest(asdict(self))

    def cost(self, input_tokens: int, output_tokens: int) -> int:
        """Round the total upward; use no speculative prompt-cache savings."""
        _integer(input_tokens, "input_tokens")
        _integer(output_tokens, "output_tokens")
        input_rate = Fraction(max(self.input_nanousd_per_million, self.cache_write_nanousd_per_million))
        output_rate = Fraction(self.output_nanousd_per_million)
        if input_tokens > self.long_context_threshold:
            input_rate *= Fraction(*self.long_input_multiplier)
            output_rate *= Fraction(*self.long_output_multiplier)
        amount = (input_tokens * input_rate + output_tokens * output_rate) / 1_000_000
        amount *= Fraction(*self.batch_multiplier) * Fraction(*self.regional_multiplier)
        return -(-amount.numerator // amount.denominator)


@dataclass(frozen=True)
class InputTokenReceipt:
    input_tokens: int
    model: str
    request_sha256: str
    receipt_sha256: str
    method: str
    provider_request_id: str | None = None

    def __post_init__(self) -> None:
        _integer(self.input_tokens, "provider_input_tokens", 1)
        _text(self.model, "count_model")
        _sha(self.request_sha256, "count_request_sha256")
        _sha(self.receipt_sha256, "count_receipt_sha256")
        if self.method != "provider_responses_input_tokens":
            raise BudgetError("budget_provider_exact_input_count_required")
        if self.provider_request_id is not None:
            _text(self.provider_request_id, "count_provider_request_id")


@dataclass(frozen=True)
class UsageReceipt:
    input_tokens: int | None
    output_tokens: int | None
    model: str | None
    request_sha256: str
    receipt_sha256: str
    complete: bool
    provider_request_id: str | None = None

    def __post_init__(self) -> None:
        for name in ("input_tokens", "output_tokens"):
            if getattr(self, name) is not None:
                _integer(getattr(self, name), name)
        _sha(self.request_sha256, "usage_request_sha256")
        _sha(self.receipt_sha256, "usage_receipt_sha256")
        if type(self.complete) is not bool:
            raise BudgetError("budget_invalid_usage_complete")
        if self.model is not None:
            _text(self.model, "usage_model")
        if self.provider_request_id is not None:
            _text(self.provider_request_id, "usage_provider_request_id")


class BudgetBook:
    """One authorization-wide ledger across corpus-specific plans and shards.

    Methods modify this in-memory projection and append hash-linked events.
    The runtime must durably retain ``last_event`` before proceeding. ``settle``
    returns a rejected, frozen record for anomalies so that this evidence can be
    persisted; it does not throw away an overrun by raising before persistence.
    ``from_dict`` replays every event, never trusts a serialized total or status.
    """

    def __init__(self, price_policy: PricePolicy, authorization_id: str, *,
                 ceiling_nanousd: int = MAX_CEILING_NANOUSD,
                 operational_limit_nanousd: int = MAX_OPERATIONAL_NANOUSD) -> None:
        _text(authorization_id, "authorization_id")
        _integer(ceiling_nanousd, "ceiling", 1)
        _integer(operational_limit_nanousd, "operational_limit", 1)
        if (ceiling_nanousd > MAX_CEILING_NANOUSD or operational_limit_nanousd > MAX_OPERATIONAL_NANOUSD
                or operational_limit_nanousd > ceiling_nanousd):
            raise BudgetError("budget_ceiling_or_margin_exceeded")
        self.price_policy = price_policy
        self.authorization_id = authorization_id
        self.ceiling_nanousd = ceiling_nanousd
        self.operational_limit_nanousd = operational_limit_nanousd
        self._entries: dict[str, dict[str, Any]] = {}
        self._tasks: dict[str, str] = {}
        self._events: list[dict[str, Any]] = []
        self._charged = 0
        self._reserved = 0
        self._frozen = False

    @property
    def charged_nanousd(self) -> int:
        return self._charged

    @property
    def reserved_nanousd(self) -> int:
        return self._reserved

    @property
    def committed_nanousd(self) -> int:
        return self._charged + self._reserved

    @property
    def available_nanousd(self) -> int:
        return max(0, self.operational_limit_nanousd - self.committed_nanousd)

    @property
    def frozen(self) -> bool:
        return self._frozen

    @property
    def last_event(self) -> dict[str, Any] | None:
        return _copy(self._events[-1]) if self._events else None

    def entry(self, request_id: str) -> dict[str, Any]:
        if request_id not in self._entries:
            raise BudgetError("budget_unknown_request")
        return _copy(self._entries[request_id])

    def _config(self) -> dict[str, Any]:
        return {"method": METHOD, "price_policy": asdict(self.price_policy),
                "authorization_id": self.authorization_id, "ceiling_nanousd": self.ceiling_nanousd,
                "operational_limit_nanousd": self.operational_limit_nanousd}

    def _record(self, action: str, value: dict[str, Any]) -> None:
        previous = self._events[-1]["sha256"] if self._events else _digest(self._config())
        event = {"sequence": len(self._events), "previous_sha256": previous, "action": action, "value": _copy(value)}
        event["sha256"] = _digest(event)
        self._events.append(event)

    def reserve(self, *, request_id: str, task_id: str, corpus_id: str, plan_id: str,
                request_sha256: str, input_count: InputTokenReceipt,
                max_output_tokens: int, price_fingerprint: str) -> dict[str, Any]:
        for name, identifier in (("request_id", request_id), ("task_id", task_id), ("corpus_id", corpus_id), ("plan_id", plan_id)):
            _text(identifier, name)
        _sha(request_sha256, "request_sha256")
        _integer(max_output_tokens, "max_output_tokens", 1)
        if (price_fingerprint != self.price_policy.fingerprint or input_count.model != self.price_policy.model
                or input_count.request_sha256 != request_sha256):
            raise BudgetError("budget_request_price_or_count_mismatch")
        value = {"request_id": request_id, "task_id": task_id, "corpus_id": corpus_id, "plan_id": plan_id,
                 "request_sha256": request_sha256, "input_count": asdict(input_count),
                 "max_output_tokens": max_output_tokens, "price_fingerprint": price_fingerprint}
        if request_id in self._entries:
            if self._entries[request_id]["request"] != value:
                raise BudgetError("budget_request_identity_conflict")
            return self.entry(request_id)
        if self.frozen:
            raise BudgetError("budget_frozen")
        if task_id in self._tasks:
            raise BudgetError("budget_automatic_retry_forbidden")
        reserved = self.price_policy.cost(input_count.input_tokens, max_output_tokens)
        if self.committed_nanousd + reserved > self.operational_limit_nanousd:
            raise BudgetError("budget_operational_limit_reached")
        self._entries[request_id] = {"request": value, "status": "reserved", "reserved_nanousd": reserved,
                                     "charged_nanousd": 0, "accepted": False, "settlement": None}
        self._tasks[task_id] = request_id
        self._reserved += reserved
        self._record("reserve", value)
        return self.entry(request_id)

    def settle(self, request_id: str, usage: UsageReceipt | None) -> dict[str, Any]:
        row = self.entry(request_id)
        settlement = asdict(usage) if usage is not None else None
        if row["status"] in {"settled", "overrun", "frozen", "confirmed_unprocessed"}:
            if row["status"] != "confirmed_unprocessed" and row["settlement"] == settlement:
                return row
            raise BudgetError("budget_conflicting_terminal_settlement")
        request = row["request"]
        if usage is not None and usage.request_sha256 != request["request_sha256"]:
            raise BudgetError("budget_usage_request_mismatch")
        if usage is None or not usage.complete or usage.input_tokens is None or usage.output_tokens is None:
            status, accepted, charge, reason = "unknown", False, 0, "missing_or_incomplete_usage"
        elif usage.model is None or usage.model != self.price_policy.model:
            status, accepted, charge, reason = "frozen", False, 0, "unverified_or_wrong_model"
            self._frozen = True
        else:
            charge = self.price_policy.cost(usage.input_tokens, usage.output_tokens)
            unexpected = (usage.input_tokens != request["input_count"]["input_tokens"]
                          or usage.output_tokens > request["max_output_tokens"])
            if charge > row["reserved_nanousd"]:
                status, accepted, reason = "overrun", False, "observed_cost_exceeds_reservation"
                self._frozen = True
            elif unexpected:
                status, accepted, charge, reason = "frozen", False, 0, "provider_token_contract_mismatch"
                self._frozen = True
            else:
                status, accepted, reason = "settled", True, None
        if status in {"settled", "overrun"}:
            self._reserved -= row["reserved_nanousd"]
            row["reserved_nanousd"] = 0
            self._charged += charge
        row.update(status=status, accepted=accepted, charged_nanousd=charge,
                   settlement=settlement, reason=reason)
        if self._entries[request_id] == row:
            return row
        self._entries[request_id] = row
        self._record("settle", {"request_id": request_id, "usage": settlement})
        return self.entry(request_id)

    def confirm_unprocessed(self, request_id: str, *, confirmation_sha256: str,
                            provider_request_id: str, confirmed_unprocessed: bool) -> dict[str, Any]:
        """Release only a provider-attested unprocessed request, never cancellation alone."""
        _sha(confirmation_sha256, "unprocessed_confirmation")
        _text(provider_request_id, "unprocessed_provider_request_id")
        if confirmed_unprocessed is not True:
            raise BudgetError("budget_confirmed_unprocessed_required")
        value = {"request_id": request_id, "confirmation_sha256": confirmation_sha256,
                 "provider_request_id": provider_request_id, "confirmed_unprocessed": True}
        row = self.entry(request_id)
        if row["status"] == "confirmed_unprocessed" and row["settlement"] == value:
            return row
        if row["status"] not in {"reserved", "unknown"}:
            raise BudgetError("budget_conflicting_terminal_settlement")
        self._reserved -= row["reserved_nanousd"]
        row.update(status="confirmed_unprocessed", reserved_nanousd=0, settlement=value,
                   accepted=False, reason="provider_confirmed_unprocessed")
        self._entries[request_id] = row
        self._record("confirm_unprocessed", value)
        return self.entry(request_id)

    def to_dict(self) -> dict[str, Any]:
        return _copy({"config": self._config(), "events": self._events})

    @classmethod
    def from_dict(cls, state: dict[str, Any]) -> BudgetBook:
        """Validate and replay persisted events without trusting mutable projections."""
        try:
            if set(state) != {"config", "events"} or not isinstance(state["events"], list):
                raise BudgetError("budget_invalid_snapshot")
            config = dict(state["config"])
            if config.pop("method") != METHOD:
                raise BudgetError("budget_wrong_method")
            price = PricePolicy(**config.pop("price_policy"))
            result = cls(price_policy=price, **config)
            for event in state["events"]:
                value = dict(event["value"])
                action = event["action"]
                previous_count = len(result._events)
                if action == "reserve":
                    value["input_count"] = InputTokenReceipt(**value["input_count"])
                    result.reserve(**value)
                elif action == "settle":
                    if value["usage"] is not None:
                        value["usage"] = UsageReceipt(**value["usage"])
                    result.settle(**value)
                elif action == "confirm_unprocessed":
                    result.confirm_unprocessed(**value)
                else:
                    raise BudgetError("budget_unknown_event_action")
                if len(result._events) != previous_count + 1 or result.last_event != event:
                    raise BudgetError("budget_event_replay_mismatch")
            return result
        except (KeyError, TypeError, AttributeError) as error:
            raise BudgetError("budget_invalid_snapshot") from error
