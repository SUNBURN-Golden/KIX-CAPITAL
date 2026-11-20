"""Shared fixtures and oracles for the seeded settlement property suite.

unittest discover collects test*.py only, so this module is not a test.
Oracles are typed in from docs/contracts/SETTLEMENT_DISTRIBUTION_F01_F03.md
sections 1-6 and 9. They are not imported from mock_settlement.py and they do
not follow its control flow.
Numbers here are synthetic KRW integers, labelled as fixtures. They are not
policy values, fee rates, a waterfall or an accounting treatment.
The author of this harness is the builder. A run is not an independent PASS.
"""

from __future__ import annotations

import json
import random
from fractions import Fraction

from mock_settlement import MockSettlement, SettlementError

SEEDS = (1, 2, 3, 5, 8, 13, 21, 34)
MOCK_STEPS = 120

# Contract section 1. Typed in, compared with the mock's constant in a test.
CONTRACT_MONEY_MAX = 10**12
ALWAYS_FALSE_FLAGS = (
    "legal_debtor_bound",
    "admission_granted",
    "right_cancelled",
    "bank_debit_observed",
    "external_return_closed",
    "funds_executed",
)

# Contract section 6. MOCK_INVARIANT is deliberately absent: it is an
# implementation error, never a caller-correctable rejection.
CONTRACT_CODES = frozenset(
    {
        "INVALID_ID",
        "INVALID_AMOUNT",
        "INVALID_NONNEGATIVE",
        "CURRENCY_UNSUPPORTED",
        "POLICY_TYPE",
        "POLICY_FIELDS",
        "POLICY_KIND",
        "POLICY_FEE_BPS",
        "POLICY_PAYEE",
        "POLICY_PAYEE_COLLISION",
        "UNKNOWN_CLAIM",
        "CLAIM_BINDING_CONFLICT",
        "SETTLEMENT_COMPONENT_MISMATCH",
        "SETTLEMENT_EXCEEDS_OPEN_RECEIVABLE",
        "STATEMENT_BINDING_CONFLICT",
        "ADJUSTMENT_REASON_REQUIRED",
        "ADJUSTMENT_REASON_UNEXPECTED",
        "DISTRIBUTION_ORDER_TYPE",
        "DISTRIBUTION_ORDER_DUPLICATE",
        "DISTRIBUTION_ORDER_MISMATCH",
        "DISTRIBUTION_ORDER_FROZEN",
        "DISTRIBUTION_BLOCKED_REFUND_BEARER_UNDEFINED",
        "REFUND_CEILING",
        "REFUND_BINDING_CONFLICT",
        "REFUND_BENEFICIARY_CONFLICT",
        "REFUND_OBLIGATION_REQUIRED",
        "REFUND_ACCEPTANCE_EXCEEDS_OBLIGATION",
        "ACCEPTANCE_BINDING_CONFLICT",
        "UNKNOWN_SETTLEMENT",
        "ILLEGAL_TRANSITION",
        "TERMINAL_IMMUTABLE",
        "IDEMPOTENCY_CONFLICT",
        "EXTERNAL_PAYMENT_UNSUPPORTED",
        "INVALID_JOURNAL",
    }
)

# Contract section 9.2: op -> (phases it may run in, phase afterwards or None).
PHASE_TABLE = {
    "authorize": (frozenset({"INITIATED"}), "AUTHORIZED"),
    "fail": (frozenset({"INITIATED", "AUTHORIZED"}), "FAILED"),
    "cancel": (frozenset({"INITIATED", "AUTHORIZED"}), "CANCELLED"),
    "capture": (frozenset({"AUTHORIZED"}), "CAPTURED"),
    "commit": (frozenset({"CAPTURED"}), "COMMITTED"),
    "observe_statement": (frozenset({"COMMITTED"}), None),
    "distribute": (frozenset({"COMMITTED"}), None),
    "bind_refund": (frozenset({"CAPTURED", "COMMITTED"}), None),
    "observe_mock_cancel_acceptance": (frozenset({"CAPTURED", "COMMITTED"}), None),
}
TERMINAL = frozenset({"FAILED", "CANCELLED"})
PHASE_RANK = {
    "INITIATED": 0,
    "AUTHORIZED": 1,
    "CAPTURED": 2,
    "COMMITTED": 3,
    "FAILED": 4,
    "CANCELLED": 4,
}

GROSS_GRID = (1, 2, 3, 9, 99, 100, 101, 9_999, 10_000, 10_001, CONTRACT_MONEY_MAX - 1, CONTRACT_MONEY_MAX)
BPS_GRID = (0, 1, 2, 5000, 9999, 10000)
RESIDUAL = "fixture-residual"
FEE = "fixture-fee"


def rng(seed: int) -> random.Random:
    return random.Random(seed)


def canon(value: object) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"))


def policy(bps: int, residual: str = RESIDUAL, fee: str = FEE) -> dict:
    return {"kind": "PRIMARY_FEE_BPS", "fee_bps": bps, "residual_payee": residual, "fee_payee": fee}


def is_money(value: object, *, positive: bool) -> bool:
    low = 1 if positive else 0
    return type(value) is int and low <= value <= CONTRACT_MONEY_MAX


def is_ident(value: object) -> bool:
    return type(value) is str and 0 < len(value) <= 100 and value.strip() == value


def oracle_split(gross: int, bps: int, residual: str = RESIDUAL, fee: str = FEE) -> dict:
    """Contract section 2. Zero-face lines are not obligations."""

    fee_face = int(Fraction(gross * bps, 10000) // 1)
    faces = {residual: gross - fee_face, fee: fee_face}
    return {payee: face for payee, face in faces.items() if face}


def take_vector(outstanding: list, available: int) -> list:
    """Contract section 4: cash in caller order, each up to its outstanding.

    Written as prefix-clipped amounts, not as the mock's running remainder.
    """

    takes = []
    before = 0
    for out in outstanding:
        takes.append(max(0, min(out, available - before)))
        before += out
    return takes


class Mirror:
    """Per-claim tally built only from the arguments of successful calls."""

    def __init__(self, claim_id, trade_id, gross, role, bps, residual, fee):
        self.claim_id = claim_id
        self.binding = (trade_id, gross, role, bps, residual, fee)
        self.gross = gross
        self.faces = oracle_split(gross, bps, residual, fee)
        self.dist = {p: 0 for p in self.faces}
        self.cancelled = {p: 0 for p in self.faces}
        self.recovery = {p: 0 for p in self.faces}
        self.cash = 0
        self.non_cash = 0
        self.stmt_gross = 0
        self.statements = {}
        self.refunds = {}
        self.refund_face = 0
        self.beneficiary = None
        self.reclassified = False
        self.accepts = {}
        self.accepted = 0
        self.order = None

    def outstanding(self, payee: str) -> int:
        return self.faces[payee] - self.dist[payee] - self.cancelled[payee]

    # --- preconditions, contract sections 1-5 ---------------------------------
    def statement_state_violations(self, mid, vals) -> set:
        known = self.statements.get(mid)
        if known is not None:
            return set() if known == vals else {"STATEMENT_BINDING_CONFLICT"}
        if self.stmt_gross + vals[0] > self.gross:
            return {"SETTLEMENT_EXCEEDS_OPEN_RECEIVABLE"}
        return set()

    def distribution_state_violations(self, order) -> set:
        found = set()
        if len(set(order)) != len(order):
            found.add("DISTRIBUTION_ORDER_DUPLICATE")
        if set(order) != set(self.faces):
            found.add("DISTRIBUTION_ORDER_MISMATCH")
        if self.order is not None and list(order) != self.order:
            found.add("DISTRIBUTION_ORDER_FROZEN")
        return found

    def refund_state_violations(self, rid, vals) -> set:
        known = self.refunds.get(rid)
        if known is not None:
            return set() if known == vals else {"REFUND_BINDING_CONFLICT"}
        found = set()
        if self.refund_face + vals[0] > self.gross:
            found.add("REFUND_CEILING")
        if self.beneficiary not in (None, vals[1]):
            found.add("REFUND_BENEFICIARY_CONFLICT")
        return found

    def acceptance_state_violations(self, sid, amount) -> set:
        known = self.accepts.get(sid)
        if known is not None:
            return set() if known == amount else {"ACCEPTANCE_BINDING_CONFLICT"}
        if self.refund_face == 0:
            return {"REFUND_OBLIGATION_REQUIRED"}
        if amount > self.refund_face - self.accepted:
            return {"REFUND_ACCEPTANCE_EXCEEDS_OBLIGATION"}
        return set()

    # --- deltas after a successful call ---------------------------------------
    def apply_statement(self, mid, vals) -> None:
        if mid in self.statements:
            return
        gross, amount, fee, tax, held, adjustment, reason = vals
        self.statements[mid] = vals
        self.stmt_gross += gross
        self.cash += amount
        self.non_cash += gross - amount

    def apply_distribution(self, order) -> dict:
        if self.order is None:
            self.order = list(order)
        available = self.cash - sum(self.dist.values())
        takes = take_vector([self.outstanding(p) for p in order], available)
        for payee, take in zip(order, takes):
            self.dist[payee] += take
        return dict(zip(order, takes))

    def apply_refund(self, rid, vals) -> None:
        if rid in self.refunds:
            return
        amount, beneficiary = vals[0], vals[1]
        first_full = amount == self.gross and self.refund_face == 0
        self.refunds[rid] = vals
        self.refund_face += amount
        self.beneficiary = beneficiary
        if first_full:
            for payee in self.faces:
                self.cancelled[payee] += self.outstanding(payee)
                self.recovery[payee] = self.dist[payee]
            self.reclassified = True

    def apply_acceptance(self, sid, amount) -> None:
        if sid in self.accepts:
            return
        self.accepts[sid] = amount
        self.accepted += amount


def check_claim_view(view: dict, mirror: Mirror | None = None) -> None:
    """Property (b): per-line identity, conservation, no shared cash."""

    lines = view["obligations"]
    assert sum(item["face"] for item in lines) == view["gross"], "faces do not sum to gross"
    for item in lines:
        assert item["outstanding"] >= 0, item
        assert item["distributed"] >= 0 and item["cancelled_unpaid"] >= 0, item
        assert item["face"] == item["distributed"] + item["cancelled_unpaid"] + item["outstanding"], item
        assert item["recovery_due"] <= item["distributed"], item
    distributed = sum(item["distributed"] for item in lines)
    assert view["distributed_cash"] == distributed
    assert distributed <= view["confirmed_cash"], "distributed exceeds confirmed cash"
    assert view["undistributed_cash"] == view["confirmed_cash"] - distributed
    assert view["confirmed_cash"] + view["non_cash_accounted"] == view["gross"] - view["receivable_open"]
    assert 0 <= view["receivable_open"] <= view["gross"]
    assert 0 <= view["refund_accepted"] <= view["refund_face"] <= view["gross"]
    assert view["pg_adjustment_outstanding"] == view["refund_accepted"]
    for flag in ALWAYS_FALSE_FLAGS:
        assert view[flag] is False, flag
    if mirror is None:
        return
    assert {item["payee"]: item["face"] for item in lines} == mirror.faces, "faces differ from the contract split"
    for item in lines:
        payee = item["payee"]
        assert item["distributed"] == mirror.dist[payee], ("distributed", payee)
        assert item["cancelled_unpaid"] == mirror.cancelled[payee], ("cancelled", payee)
        assert item["recovery_due"] == mirror.recovery[payee], ("recovery", payee)
    assert view["confirmed_cash"] == mirror.cash, "claim cash differs from its own statements"
    assert view["non_cash_accounted"] == mirror.non_cash
    assert view["refund_face"] == mirror.refund_face
    assert view["refund_accepted"] == mirror.accepted
    assert view["fixture_reclassified"] is mirror.reclassified
    assert view["distribution_order"] == mirror.order


# --- generators ---------------------------------------------------------------

BAD_MONEY = (0, -1, CONTRACT_MONEY_MAX + 1, True, "5", None, 1.5)
BAD_IDENT = ("", " x", "x ", None, 5)


def split_money(r: random.Random, gross: int) -> tuple:
    """Random (amount, fee, tax, held, adjustment) summing to gross."""

    cuts = sorted(r.randint(0, gross) for _ in range(4))
    parts = [b - a for a, b in zip([0] + cuts, cuts + [gross])]
    r.shuffle(parts)
    return tuple(parts)


def statement_vals(gross, amount, fee, tax, held, adjustment, reason) -> tuple:
    return (gross, amount, fee, tax, held, adjustment, reason)


def statement_kwargs(mid, vals) -> dict:
    gross, amount, fee, tax, held, adjustment, reason = vals
    return dict(
        movement_id=mid,
        gross=gross,
        amount=amount,
        fee=fee,
        tax=tax,
        held=held,
        adjustment=adjustment,
        adjustment_reason=reason,
    )


def statement_static(mid, vals) -> set:
    """Argument-only violations (contract sections 1 and 3)."""

    gross, amount, fee, tax, held, adjustment, reason = vals
    found = set()
    if not is_ident(mid):
        found.add("INVALID_ID")
    if not is_money(gross, positive=True):
        found.add("INVALID_AMOUNT")
    if not all(is_money(v, positive=False) for v in (amount, fee, tax, held, adjustment)):
        found.add("INVALID_NONNEGATIVE")
    if found:
        return found
    if adjustment:
        if not is_ident(reason):
            found.add("ADJUSTMENT_REASON_REQUIRED")
    elif reason is not None:
        found.add("ADJUSTMENT_REASON_UNEXPECTED")
    if not found and amount + fee + tax + held + adjustment != gross:
        found.add("SETTLEMENT_COMPONENT_MISMATCH")
    return found


class MockDriver:
    """Seeded random call driver over MockSettlement with contract oracles.

    Raises AssertionError on the first oracle failure. Any SettlementError that
    the contract does not allow for the call is also reported as AssertionError.
    """

    CLAIM_IDS = ("claim-tiny", "claim-mid", "claim-max")

    def __init__(self, seed: int, steps: int = MOCK_STEPS):
        self.r = rng(seed)
        self.steps = steps
        self.mock = MockSettlement()
        self.mirrors: dict = {}
        self.counts: dict = {}

    # claim setup ------------------------------------------------------------
    def claim_spec(self, claim_id: str) -> tuple:
        r = self.r
        gross = {
            "claim-tiny": r.choice((1, 2, 3, 7, 20)),
            "claim-mid": r.randint(100, 100_000),
            "claim-max": CONTRACT_MONEY_MAX,
        }[claim_id]
        bps = r.choice(BPS_GRID + (r.randint(0, 10000),))
        return (f"trade-{claim_id}", gross, "fixture-debtor", bps, RESIDUAL, FEE)

    def recognize(self, claim_id, spec, *, currency="KRW", bad_policy=None) -> None:
        trade, gross, role, bps, residual, fee = spec
        pol = policy(bps, residual, fee) if bad_policy is None else bad_policy
        static = set()
        if currency != "KRW":
            static.add("CURRENCY_UNSUPPORTED")
        if bad_policy is not None:
            static.add(bad_policy["_expect"])
            pol = {k: v for k, v in bad_policy.items() if k != "_expect"}
        if not is_money(gross, positive=True):
            static.add("INVALID_AMOUNT")
        expected = set(static)
        known = self.mirrors.get(claim_id)
        if not expected and known is not None and known.binding != spec:
            expected = {"CLAIM_BINDING_CONFLICT"}
        result = self.call(
            "recognize_claim",
            expected,
            claim_id,
            trade_id=trade,
            gross=gross,
            debtor_role=role,
            policy=pol,
            currency=currency,
        )
        if result is None and known is None:
            try:
                self.mock.view(claim_id)
            except SettlementError as error:
                assert error.code == "UNKNOWN_CLAIM"
            else:
                raise AssertionError("a rejected recognize_claim opened a claim")
        if result is not None and known is None:
            self.mirrors[claim_id] = Mirror(claim_id, *spec)
        if result is not None:
            assert result["duplicate"] is (known is not None)

    # one call with snapshot + oracle ----------------------------------------
    def snapshot(self) -> dict:
        return {cid: canon(self.mock.view(cid)) for cid in self.mirrors}

    def call(self, op, expected, *args, **kwargs):
        """Run one call. expected empty => must succeed; else code in expected."""

        before = self.snapshot()
        try:
            result = getattr(self.mock, op)(*args, **kwargs)
        except SettlementError as error:
            assert error.code in CONTRACT_CODES, f"{op}: code {error.code} is not in the contract table"
            assert expected, f"{op}: unexpected rejection {error.code}"
            assert error.code in expected, f"{op}: {error.code} not in {sorted(expected)}"
            assert self.snapshot() == before, f"{op}: view changed after a rejected call ({error.code})"
            self.counts[error.code] = self.counts.get(error.code, 0) + 1
            self.check_all()
            return None
        assert not expected, f"{op}: accepted although the contract rejects it ({sorted(expected)})"
        self.counts["ok:" + op] = self.counts.get("ok:" + op, 0) + 1
        return result

    def check_all(self) -> None:
        for cid, mirror in self.mirrors.items():
            check_claim_view(self.mock.view(cid), mirror)

    # step generators ----------------------------------------------------------
    def step(self) -> None:
        r = self.r
        cid = r.choice(self.CLAIM_IDS * 4 + ("claim-ghost",))
        op = r.choice(
            ("recognize", "statement", "statement", "statement", "distribute", "distribute", "refund", "accept", "accept")
        )
        mirror = self.mirrors.get(cid)
        if op == "recognize":
            self.step_recognize(cid, mirror)
            return
        if mirror is None:
            self.step_unknown(cid, op)
            return
        {"statement": self.step_statement, "distribute": self.step_distribute, "refund": self.step_refund, "accept": self.step_accept}[op](cid, mirror)
        self.check_all()

    def step_recognize(self, cid, mirror) -> None:
        r = self.r
        if cid == "claim-ghost":
            cid = r.choice(self.CLAIM_IDS)
            mirror = self.mirrors.get(cid)
        spec = mirror.binding if mirror is not None else self.claim_spec(cid)
        roll = r.random()
        if mirror is not None and roll < 0.3:
            self.recognize(cid, spec)  # identical repeat
        elif mirror is not None and roll < 0.6:
            trade, gross, role, bps, residual, fee = spec
            field = r.choice(("trade", "role", "bps", "residual", "fee"))
            if field == "trade":
                trade += "-x"
            elif field == "role":
                role += "-x"
            elif field == "bps":
                bps = bps - 1 if bps else 1
            elif field == "residual":
                residual += "-x"
            else:
                fee += "-x"
            self.recognize(cid, (trade, gross, role, bps, residual, fee))
        elif roll < 0.8:
            trade, gross, role, bps, residual, fee = spec
            variant = r.choice(
                (
                    ("gross", r.choice((0, -1, CONTRACT_MONEY_MAX + 1, True))),
                    ("bps", r.choice((-1, 10001, True, "5"))),
                    ("same_payee", None),
                    ("currency", None),
                )
            )
            if variant[0] == "gross":
                self.recognize(cid, (trade, variant[1], role, bps, residual, fee))
            elif variant[0] == "bps":
                bad = dict(policy(bps, residual, fee), fee_bps=variant[1], _expect="POLICY_FEE_BPS")
                self.recognize(cid, spec, bad_policy=bad)
            elif variant[0] == "same_payee":
                bad = dict(policy(bps, residual, residual), _expect="POLICY_PAYEE_COLLISION")
                self.recognize(cid, spec, bad_policy=bad)
            else:
                self.recognize(cid, spec, currency="USD")
        elif mirror is None:
            self.recognize(cid, spec)
        self.check_all()

    def step_unknown(self, cid, op) -> None:
        # Any non-recognize call on a claim that was never opened.
        calls = {
            "statement": ("observe_settlement_statement", statement_kwargs("m-x", (1, 1, 0, 0, 0, 0, None))),
            "distribute": ("apply_distribution", {"order": [RESIDUAL, FEE]}),
            "refund": ("bind_refund", dict(refund_id="r-x", amount=1, beneficiary_role="b", reason="why")),
            "accept": ("observe_mock_cancel_acceptance", dict(source_id="a-x", amount=1)),
        }
        name, kwargs = calls[op]
        self.call(name, {"UNKNOWN_CLAIM"}, cid, **kwargs)

    def step_statement(self, cid, mirror) -> None:
        r = self.r
        room = mirror.gross - mirror.stmt_gross
        known = sorted(mirror.statements)
        roll = r.random()
        reason = None
        if known and roll < 0.25:
            mid = r.choice(known)
            vals = mirror.statements[mid]
            if r.random() < 0.5:
                # same movement id, one unit shifted between components
                gross, amount, fee, tax, held, adjustment, reason = vals
                if amount:
                    vals = (gross, amount - 1, fee + 1, tax, held, adjustment, reason) if fee < CONTRACT_MONEY_MAX else vals
        elif roll < 0.45:
            mid = r.choice(("m-bad", " m", "", None))
            vals = (5, 5, 0, 0, 0, 0, None)
            if mid == "m-bad":
                vals = r.choice(
                    (
                        (r.choice(BAD_MONEY), 1, 0, 0, 0, 0, None),
                        (10, r.choice(BAD_MONEY[1:]), 0, 0, 0, 0, None),
                        (10, 3, 3, 3, 3, 0, None),  # sum 12 != 10
                        (10, 5, 0, 0, 0, 5, None),  # adjustment without reason
                        (10, 10, 0, 0, 0, 0, "why"),  # reason without adjustment
                    )
                )
        else:
            mid = f"m-{len(mirror.statements)}-{r.randint(0, 9)}"
            if mid in mirror.statements:
                mid += "-n"
            over = room == 0 or r.random() < 0.15
            gross = room + 1 if over and room < CONTRACT_MONEY_MAX else r.randint(1, max(1, room))
            gross = min(gross, CONTRACT_MONEY_MAX)
            parts = split_money(r, gross)
            if r.random() < 0.5:
                parts = (gross, 0, 0, 0, 0) if r.random() < 0.5 else parts
            amount, fee, tax, held, adjustment = parts
            reason = "fixture-adjustment" if adjustment else None
            vals = (gross, amount, fee, tax, held, adjustment, reason)
        expected = statement_static(mid, vals)
        if not expected:
            expected = mirror.statement_state_violations(mid, vals)
        result = self.call(
            "observe_settlement_statement", expected, cid, **statement_kwargs(mid, vals)
        )
        if result is not None:
            was_known = mid in mirror.statements
            assert result["duplicate"] is was_known and result["applied"] is None
            mirror.apply_statement(mid, vals)

    def step_distribute(self, cid, mirror) -> None:
        r = self.r
        payees = sorted(mirror.faces)
        order = list(payees)
        r.shuffle(order)
        if mirror.order is not None and r.random() < 0.7:
            order = list(mirror.order)
        roll = r.random()
        if roll < 0.12:
            order = order + [order[0]]
        elif roll < 0.22:
            order = order[:-1] if len(order) > 1 else ["stranger"]
        elif roll < 0.3:
            order = "not-a-list"
        static = set()
        if type(order) is not list:
            static.add("DISTRIBUTION_ORDER_TYPE")
        expected = static or mirror.distribution_state_violations(order)
        result = self.call("apply_distribution", expected, cid, order=order)
        if result is not None:
            applied = mirror.apply_distribution(order)
            assert result["applied"] == applied, "applied amounts differ from the contract prefix rule"
            assert result["duplicate"] is False

    def step_refund(self, cid, mirror) -> None:
        r = self.r
        known = sorted(mirror.refunds)
        beneficiary = mirror.beneficiary or "fixture-buyer"
        roll = r.random()
        if known and roll < 0.25:
            rid = r.choice(known)
            vals = mirror.refunds[rid]
            if r.random() < 0.5:
                vals = (vals[0], vals[1], vals[2] + "-x")
        elif roll < 0.35:
            rid = "r-bad"
            vals = (r.choice(BAD_MONEY), beneficiary, "why")
        elif roll < 0.45:
            rid = f"r-{len(mirror.refunds)}-b"
            vals = (1, beneficiary + "-other", "why")
        else:
            rid = f"r-{len(mirror.refunds)}-{r.randint(0, 9)}"
            if rid in mirror.refunds:
                rid += "-n"
            if not mirror.refunds and r.random() < 0.35:
                amount = mirror.gross  # first full-gross refund
            else:
                amount = r.randint(1, max(1, mirror.gross - mirror.refund_face + (1 if r.random() < 0.15 else 0)))
                amount = min(amount, CONTRACT_MONEY_MAX)
            vals = (amount, beneficiary, "fixture-reason")
        expected = set()
        if not is_money(vals[0], positive=True):
            expected.add("INVALID_AMOUNT")
        if not expected:
            expected = mirror.refund_state_violations(rid, vals)
        result = self.call(
            "bind_refund", expected, cid, refund_id=rid, amount=vals[0], beneficiary_role=vals[1], reason=vals[2]
        )
        if result is not None:
            assert result["duplicate"] is (rid in mirror.refunds) and result["applied"] is None
            mirror.apply_refund(rid, vals)

    def step_accept(self, cid, mirror) -> None:
        r = self.r
        known = sorted(mirror.accepts)
        roll = r.random()
        if known and roll < 0.25:
            sid = r.choice(known)
            amount = mirror.accepts[sid] + (1 if r.random() < 0.4 and mirror.accepts[sid] < CONTRACT_MONEY_MAX else 0)
        elif roll < 0.35:
            sid, amount = "a-bad", r.choice(BAD_MONEY)
        else:
            sid = f"a-{len(mirror.accepts)}-{r.randint(0, 9)}"
            if sid in mirror.accepts:
                sid += "-n"
            left = mirror.refund_face - mirror.accepted
            amount = r.randint(1, max(1, left + (1 if r.random() < 0.15 else 0)))
            amount = min(amount, CONTRACT_MONEY_MAX)
        expected = set()
        if not is_money(amount, positive=True):
            expected.add("INVALID_AMOUNT")
        if not expected:
            expected = mirror.acceptance_state_violations(sid, amount)
        result = self.call("observe_mock_cancel_acceptance", expected, cid, source_id=sid, amount=amount)
        if result is not None:
            assert result["duplicate"] is (sid in mirror.accepts) and result["applied"] is None
            mirror.apply_acceptance(sid, amount)

    def run(self) -> dict:
        for cid in self.CLAIM_IDS:
            self.recognize(cid, self.claim_spec(cid))
        self.check_all()
        for _ in range(self.steps):
            self.step()
        self.check_all()
        return self.counts


# --- refund corpus (plan-settlement-multi-payee-refund-corpus) ----------------

BEARER_RANK = {"NONE": 0, "REQUESTER": 1, "FIXTURE_FULL_GROSS_RECLASS": 2}
REFUND_OPS = ("bind_refund", "observe_mock_cancel_acceptance")


def check_refund_view(view: dict) -> None:
    """Contract section 5 and section 7.6 (B5) refund predicates.

    Typed from the contract, not from the mock's control flow: the bearer
    label is derived only from refund_face and the reclass flag; a reclass
    reserves each payee's unpaid face as cancelled_unpaid and its already
    paid cash as recovery_due; a partial sum that reaches gross never
    reclassifies (asserted through the flag, not through a bearer rule).
    Under B5 a partial refund never blocks distribution.
    """

    face = view["refund_face"]
    accepted = view["refund_accepted"]
    gross = view["gross"]
    assert view["refund_outstanding"] == face - accepted
    assert view["pg_adjustment_outstanding"] == accepted
    assert 0 <= accepted <= face <= gross
    reclassified = view["fixture_reclassified"]
    bearer = view["refund_bearer_policy"]
    assert bearer == (
        "FIXTURE_FULL_GROSS_RECLASS" if reclassified else "REQUESTER" if face else "NONE"
    ), bearer
    assert view["distribution_blocked"] is False
    lines = view["obligations"]
    assert view["recovery_due"] == sum(item["recovery_due"] for item in lines)
    if reclassified:
        assert face == gross, "a first full-gross refund is the only reclass"
        for item in lines:
            assert item["outstanding"] == 0, item
            assert item["cancelled_unpaid"] == item["face"] - item["distributed"], item
            assert item["recovery_due"] == item["distributed"], item
        assert view["recovery_due"] == view["distributed_cash"]
    else:
        for item in lines:
            assert item["cancelled_unpaid"] == 0 and item["recovery_due"] == 0, item
        assert view["recovery_due"] == 0
    assert view["provenance"] == "MOCK_SETTLEMENT_ONLY"


class RefundCorpusDriver(MockDriver):
    """Seeded mock driver weighted toward the refund family.

    Each claim carries its own payee label pair, so obligations never share
    a payee string across claims. The oracle checks per-payee reservation
    and bearer monotonicity after every call, not only at the end.
    """

    CLAIM_IDS = ("claim-one", "claim-two", "claim-max")

    def __init__(self, seed: int, steps: int = MOCK_STEPS):
        super().__init__(seed, steps)
        self.bearer: dict = {}
        self.reclassed: set = set()

    def bump(self, name: str) -> None:
        self.counts[name] = self.counts.get(name, 0) + 1

    def claim_spec(self, claim_id: str) -> tuple:
        r = self.r
        tag = claim_id.rsplit("-", 1)[-1]
        gross = {
            "claim-one": r.choice((1, 2, 3, 7, 20)),
            "claim-two": r.randint(100, 100_000),
            "claim-max": CONTRACT_MONEY_MAX,
        }[claim_id]
        bps = r.choice((0, 1, 2, 5000, 9999, 10000, r.randint(0, 10000)))
        return (f"trade-{claim_id}", gross, "fixture-debtor", bps, f"res-{tag}", f"fee-{tag}")

    def recognize(self, claim_id, spec, **kwargs) -> None:
        had = claim_id in self.mirrors
        super().recognize(claim_id, spec, **kwargs)
        mirror = self.mirrors.get(claim_id)
        if not had and mirror is not None:
            self.bump(f"lines:{len(mirror.faces)}")

    def check_all(self) -> None:
        for cid, mirror in self.mirrors.items():
            view = self.mock.view(cid)
            check_claim_view(view, mirror)
            check_refund_view(view)
            rank = BEARER_RANK[view["refund_bearer_policy"]]
            prev = self.bearer.get(cid)
            if prev is not None:
                # Contract section 5: reclass needs refund_face == 0, so only
                # NONE can move, and nothing leaves REQUESTER or the reclass.
                assert rank == prev or prev == 0, (cid, prev, rank)
            self.bearer[cid] = rank

    def step(self) -> None:
        r = self.r
        cid = r.choice(self.CLAIM_IDS * 4 + ("claim-ghost",))
        op = r.choice(
            (
                "recognize",
                "statement",
                "statement",
                "distribute",
                "fill",
                "partreclass",
                "refund",
                "refund",
                "refund",
                "accept",
                "accept",
                "replay",
            )
        )
        mirror = self.mirrors.get(cid)
        if op == "recognize":
            self.step_recognize(cid, mirror)
            return
        if mirror is None:
            self.step_unknown(cid, "refund" if op in ("fill", "partreclass", "replay") else op)
            return
        {
            "statement": self.step_statement,
            "distribute": self.step_distribute,
            "fill": self.step_fill,
            "partreclass": self.step_partial_reclass,
            "refund": self.step_refund,
            "accept": self.step_accept,
            "replay": self.step_replay,
        }[op](cid, mirror)
        self.check_all()

    def step_fill(self, cid, mirror) -> None:
        """Close the open receivable in one movement, then often distribute."""
        r = self.r
        room = mirror.gross - mirror.stmt_gross
        if room <= 0:
            self.step_distribute(cid, mirror)
            return
        mid = f"m-fill-{len(mirror.statements)}"
        vals = (room, room, 0, 0, 0, 0, None)
        expected = statement_static(mid, vals) or mirror.statement_state_violations(mid, vals)
        result = self.call("observe_settlement_statement", expected, cid, **statement_kwargs(mid, vals))
        if result is None:
            return
        was_known = mid in mirror.statements
        assert result["duplicate"] is was_known and result["applied"] is None
        mirror.apply_statement(mid, vals)
        if was_known or r.random() >= 0.6:
            return
        order = list(mirror.order) if mirror.order is not None else sorted(mirror.faces)
        result = self.call("apply_distribution", mirror.distribution_state_violations(order), cid, order=order)
        if result is not None:
            applied = mirror.apply_distribution(order)
            assert result["applied"] == applied and result["duplicate"] is False

    def step_refund(self, cid, mirror) -> None:
        r = self.r
        if 0 < mirror.refund_face < mirror.gross and r.random() < 0.15:
            # Top up to exactly gross: contract section 5 never reclassifies
            # a partial sum, so the claim stays bearer-REQUESTER (B5) and
            # distribution keeps proceeding.
            rid = f"r-top-{len(mirror.refunds)}"
            vals = (mirror.gross - mirror.refund_face, mirror.beneficiary, "fixture-reason")
            expected = mirror.refund_state_violations(rid, vals)
            result = self.call(
                "bind_refund",
                expected,
                cid,
                refund_id=rid,
                amount=vals[0],
                beneficiary_role=vals[1],
                reason=vals[2],
            )
            if result is not None:
                assert result["duplicate"] is (rid in mirror.refunds) and result["applied"] is None
                mirror.apply_refund(rid, vals)
                assert not mirror.reclassified, "a partial sum to gross must not reclassify"
                self.bump("partial-sum-to-gross")
            return
        dist_before = sum(mirror.dist.values())
        super().step_refund(cid, mirror)
        if mirror.reclassified and cid not in self.reclassed:
            self.reclassed.add(cid)
            bucket = "0" if dist_before == 0 else ("full" if dist_before == mirror.gross else "partial")
            self.bump("reclass@" + bucket)

    def step_partial_reclass(self, cid, mirror) -> None:
        """Distribute partial cash, then bind the first full-gross refund."""
        r = self.r
        if mirror.refunds:
            self.step_refund(cid, mirror)
            return
        room = mirror.gross - mirror.stmt_gross
        if room >= 2:
            # Confirmed cash lands strictly below the face sum, so the
            # distribution that follows leaves at least one payee short.
            amount = r.randint(1, room - 1)
            vals = (room, amount, room - amount, 0, 0, 0, None)
            mid = f"m-pd-{len(mirror.statements)}"
            expected = statement_static(mid, vals) or mirror.statement_state_violations(mid, vals)
            result = self.call("observe_settlement_statement", expected, cid, **statement_kwargs(mid, vals))
            if result is not None:
                assert result["duplicate"] is (mid in mirror.statements) and result["applied"] is None
                mirror.apply_statement(mid, vals)
        order = list(mirror.order) if mirror.order is not None else sorted(mirror.faces)
        result = self.call("apply_distribution", mirror.distribution_state_violations(order), cid, order=order)
        if result is not None:
            applied = mirror.apply_distribution(order)
            assert result["applied"] == applied and result["duplicate"] is False
        dist = sum(mirror.dist.values())
        rid = f"r-full-{len(mirror.refunds)}"
        vals = (mirror.gross, "fixture-buyer", "fixture-reason")
        result = self.call(
            "bind_refund",
            mirror.refund_state_violations(rid, vals),
            cid,
            refund_id=rid,
            amount=vals[0],
            beneficiary_role=vals[1],
            reason=vals[2],
        )
        if result is not None:
            assert result["duplicate"] is False and result["applied"] is None
            mirror.apply_refund(rid, vals)
            self.reclassed.add(cid)
            bucket = "0" if dist == 0 else ("full" if dist == mirror.gross else "partial")
            self.bump("reclass@" + bucket)

    def step_replay(self, cid, mirror) -> None:
        """Re-issue one known binding verbatim: duplicate, no second effect."""
        r = self.r
        pools = [
            kind
            for kind, store in (
                ("statement", mirror.statements),
                ("refund", mirror.refunds),
                ("accept", mirror.accepts),
            )
            if store
        ]
        if not pools:
            self.step_refund(cid, mirror)
            return
        kind = r.choice(pools)
        if kind == "statement":
            mid = r.choice(sorted(mirror.statements))
            result = self.call(
                "observe_settlement_statement",
                set(),
                cid,
                **statement_kwargs(mid, mirror.statements[mid]),
            )
            assert result is not None and result["duplicate"] is True and result["applied"] is None
            mirror.apply_statement(mid, mirror.statements[mid])
        elif kind == "refund":
            rid = r.choice(sorted(mirror.refunds))
            amount, beneficiary, reason = mirror.refunds[rid]
            result = self.call(
                "bind_refund",
                set(),
                cid,
                refund_id=rid,
                amount=amount,
                beneficiary_role=beneficiary,
                reason=reason,
            )
            assert result is not None and result["duplicate"] is True and result["applied"] is None
            mirror.apply_refund(rid, mirror.refunds[rid])
        else:
            sid = r.choice(sorted(mirror.accepts))
            result = self.call(
                "observe_mock_cancel_acceptance",
                set(),
                cid,
                source_id=sid,
                amount=mirror.accepts[sid],
            )
            assert result is not None and result["duplicate"] is True and result["applied"] is None
            mirror.apply_acceptance(sid, mirror.accepts[sid])
        self.bump("replay:" + kind)


# --- SettlementMachine driver -------------------------------------------------

MACHINE_STEPS = 80
MACHINE_CHECKPOINT = 10
SIDS = ("set-1", "set-2", "set-3")
NATURAL_NEXT = {
    None: ("initiate",),
    "INITIATED": ("authorize",) * 9 + ("cancel", "fail"),
    "AUTHORIZED": ("capture",) * 9 + ("cancel", "fail"),
    "CAPTURED": ("commit", "commit", "commit", "bind_refund", "observe_mock_cancel_acceptance"),
    "COMMITTED": (
        "observe_statement",
        "observe_statement",
        "distribute",
        "distribute",
        "bind_refund",
        "observe_mock_cancel_acceptance",
        "observe_mock_cancel_acceptance",
        "reconcile",
    ),
}
ALL_OPS = ("initiate",) + tuple(sorted(PHASE_TABLE)) + ("reconcile",)


def from_phase_table(op: str, phase: str | None) -> bool:
    """Contract section 9.2: may this op run in this phase (ignoring arguments)?"""

    if op == "initiate":
        return phase is None
    if op == "reconcile":
        return phase is not None
    return phase in PHASE_TABLE[op][0]


class MachineDriver:
    """Seeded command driver over SettlementMachine.

    Checks (e): rejected commands move nothing, restore(export_journal())
    reproduces the machine, replays of a key return the first result.
    Raises AssertionError on the first oracle failure.
    """

    def __init__(self, seed: int, steps: int = MACHINE_STEPS):
        from settlement_fsm import SettlementMachine

        self.machine_type = SettlementMachine
        self.r = rng(seed)
        self.steps = steps
        self.m = SettlementMachine()
        self.accepted: dict = {}
        self.rejected: dict = {}
        self.counts: dict = {}
        self.serial = 0
        self.rank = {}

    # helpers ----------------------------------------------------------------
    def bump(self, name: str) -> None:
        self.counts[name] = self.counts.get(name, 0) + 1

    def new_key(self) -> str:
        self.serial += 1
        return f"key-{self.serial}"

    def phase(self, sid: str):
        try:
            return self.m.view(sid)["phase"]
        except SettlementError as error:
            assert error.code == "UNKNOWN_SETTLEMENT", error.code
            return None

    def claim(self, sid: str):
        try:
            return self.m.view(sid)["claim"]
        except SettlementError:
            return None

    # command construction -----------------------------------------------------
    def build(self, op: str, sid: str) -> tuple:
        """Return (kwargs, wellformed)."""

        r = self.r
        bad = r.random() < 0.12
        claim = self.claim(sid)
        if op == "initiate":
            gross = r.choice((1, 3, 99, 10_000, r.randint(1, 100_000), CONTRACT_MONEY_MAX))
            kwargs = dict(
                trade_id=f"trade-{sid}",
                gross=gross,
                debtor_role="fixture-debtor",
                policy=policy(r.choice(BPS_GRID + (r.randint(0, 10000),))),
            )
            if bad:
                kwargs["gross"] = r.choice(BAD_MONEY)
            return kwargs, not bad
        if op in ("authorize", "capture", "reconcile"):
            return {}, True
        if op in ("fail", "cancel"):
            return {"reason": r.choice(BAD_IDENT) if bad else "fixture-reason"}, not bad
        if op in ("commit", "observe_statement"):
            try:
                case_gross = self.m.view(sid)["gross"]
            except SettlementError:
                case_gross = 100
            room = case_gross if claim is None else claim["receivable_open"]
            if op == "commit":
                room = case_gross
            over = room == 0 or r.random() < 0.12
            gross = min(room + 1, CONTRACT_MONEY_MAX) if over and room < CONTRACT_MONEY_MAX else r.randint(1, max(1, room))
            amount, fee, tax, held, adjustment = split_money(r, gross)
            if r.random() < 0.2:
                amount, fee, tax, held, adjustment = 0, gross, 0, 0, 0  # zero-cash statement
            kwargs = statement_kwargs(
                f"mv-{self.serial}", (gross, amount, fee, tax, held, adjustment, "fixture-adjustment" if adjustment else None)
            )
            if bad:
                kwargs["fee"] = kwargs["fee"] + 1  # breaks the component identity
            return kwargs, not bad
        if op == "distribute":
            payees = sorted(item["payee"] for item in claim["obligations"]) if claim else [RESIDUAL, FEE]
            order = list(payees)
            r.shuffle(order)
            if claim and claim["distribution_order"] and r.random() < 0.7:
                order = list(claim["distribution_order"])
            if bad:
                order = r.choice(("not-a-list", order + order[:1], ["stranger"]))
            return {"order": order}, not bad
        if op == "bind_refund":
            gross = self.m.view(sid)["gross"] if self.phase(sid) else 10
            left = gross - (claim["refund_face"] if claim else 0)
            amount = gross if (claim and claim["refund_face"] == 0 and r.random() < 0.3) else r.randint(1, max(1, left))
            if bad:
                amount = r.choice(BAD_MONEY)
            return dict(refund_id=f"rf-{self.serial}", amount=amount, beneficiary_role="fixture-buyer", reason="fixture-reason"), not bad
        if op == "observe_mock_cancel_acceptance":
            left = (claim["refund_outstanding"] if claim else 1) or 1
            # Over-acceptance probe, as in RefundCorpusDriver.step_accept:
            # keeps REFUND_ACCEPTANCE_EXCEEDS_OBLIGATION deliberately reachable.
            amount = r.randint(1, max(1, left + (1 if r.random() < 0.15 else 0)))
            if bad:
                amount = r.choice(BAD_MONEY)
            return dict(source_id=f"ac-{self.serial}", amount=amount), not bad
        raise AssertionError(op)

    def pick(self) -> tuple:
        r = self.r
        live = [s for s in SIDS if self.phase(s) not in TERMINAL]
        sid = r.choice(live + list(SIDS) + ["set-ghost"] if r.random() < 0.9 else SIDS)
        phase = self.phase(sid)
        if phase in TERMINAL or r.random() < 0.2:
            op = r.choice(ALL_OPS)
        else:
            op = r.choice(NATURAL_NEXT[phase])
        return op, sid

    # one command ----------------------------------------------------------------
    def run_command(self, op, sid, kwargs, key, *, wellformed, replay_of=None):
        m = self.m
        digest, journal = m.state_digest(), m.export_journal()
        phase_before = self.phase(sid)
        try:
            result = getattr(m, op)(sid, idempotency_key=key, **kwargs)
        except SettlementError as error:
            code = error.code
            assert code in CONTRACT_CODES, f"{op}: {code} is not in the contract table"
            assert m.state_digest() == digest, f"{op}: state_digest moved after a rejected command ({code})"
            assert m.export_journal() == journal, f"{op}: journal changed after a rejected command ({code})"
            if replay_of is None and wellformed and op != "reject_external":
                if not from_phase_table(op, phase_before) and phase_before is not None:
                    want = "TERMINAL_IMMUTABLE" if phase_before in TERMINAL else "ILLEGAL_TRANSITION"
                    if op not in ("reconcile",):
                        assert code == want, f"{op} in {phase_before}: {code} != {want}"
                if phase_before is None and op not in ("initiate", "reconcile"):
                    assert code == "UNKNOWN_SETTLEMENT", f"{op} on an unknown id: {code}"
            if replay_of is None and code != "DISTRIBUTION_ORDER_TYPE":
                self.rejected[key] = (op, sid, kwargs, code)
            self.bump("reject:" + code)
            return None, code
        # accepted or replayed
        if replay_of is not None:
            assert result["duplicate"] is True and result["applied"] is None, f"{op}: replay was not a duplicate"
            assert result["settlement"] == replay_of, f"{op}: replay differs from the first result"
            assert m.state_digest() == digest and m.export_journal() == journal, f"{op}: replay moved state"
            self.bump("replay:" + op)
            return result, None
        assert result["duplicate"] is False
        assert from_phase_table(op, phase_before), f"{op} accepted in phase {phase_before}"
        after = self.phase(sid)
        nxt = "INITIATED" if op == "initiate" else (PHASE_TABLE[op][1] if op in PHASE_TABLE else None)
        assert after == (nxt or phase_before), f"{op}: phase {phase_before} -> {after}"
        assert PHASE_RANK[after] >= PHASE_RANK.get(phase_before, -1), "phase moved backwards"
        if op == "reconcile":
            assert result["matched"] is True
            assert m.state_digest() == digest and m.export_journal() == journal, "reconcile entered the journal"
            self.accepted[key] = (op, sid, kwargs, result["settlement"])
        else:
            entries = m.export_journal()
            assert len(entries) == len(journal) + 1 and entries[:-1] == journal, f"{op}: journal grew by other than one entry"
            last = entries[-1]
            assert (last["op"], last["idempotency_key"], last["settlement_id"]) == (op, key, sid)
            assert m.state_digest() != digest, f"{op}: accepted but digest unchanged"
            self.accepted[key] = (op, sid, kwargs, result["settlement"])
        self.bump("ok:" + op)
        return result, None

    def check_views(self) -> None:
        for sid in SIDS:
            if self.phase(sid) is None:
                continue
            view = self.m.view(sid)
            for flag in ALWAYS_FALSE_FLAGS + ("provider_authorization_executed", "durable"):
                assert view[flag] is False, flag
            assert view["external_payment"] == "UNSUPPORTED"
            assert (view["claim"] is not None) == (view["phase"] in ("CAPTURED", "COMMITTED")), "claim/phase mismatch"
            if view["claim"] is not None:
                check_claim_view(view["claim"])
            assert PHASE_RANK[view["phase"]] >= self.rank.get(sid, 0), "phase moved backwards"
            self.rank[sid] = PHASE_RANK[view["phase"]]

    def check_restore(self) -> None:
        m = self.m
        restored = self.machine_type.restore(m.export_journal())
        assert restored.state_digest() == m.state_digest(), "restore(export_journal()) changed state_digest"
        assert restored.canonical_state() == m.canonical_state(), "restore(export_journal()) changed canonical_state"
        digest = restored.state_digest()
        for key, (op, sid, kwargs, settlement) in sorted(self.accepted.items()):
            if op == "reconcile":
                continue  # receipts are process-local (contract section 9.4)
            try:
                result = getattr(restored, op)(sid, idempotency_key=key, **kwargs)
            except SettlementError as error:
                raise AssertionError(f"restored machine rejected the replay of {key}: {error.code}") from error
            assert result["duplicate"] is True and result["settlement"] == settlement, f"restored replay of {key}"
        assert restored.state_digest() == digest, "replays on the restored machine moved state"
        self.bump("restore-check")

    def step(self) -> None:
        r = self.r
        roll = r.random()
        if roll < 0.12 and self.accepted:
            key = r.choice(sorted(self.accepted))
            op, sid, kwargs, settlement = self.accepted[key]
            self.run_command(op, sid, kwargs, key, wellformed=True, replay_of=settlement)
        elif roll < 0.2 and self.rejected:
            key = r.choice(sorted(self.rejected))
            op, sid, kwargs, code = self.rejected[key]
            _, got = self.run_command(op, sid, kwargs, key, wellformed=False, replay_of=None)
            assert got == code, f"rejected key replay: {got} != {code}"
        elif roll < 0.28 and (self.accepted or self.rejected):
            key = r.choice(sorted(set(self.accepted) | set(self.rejected)))
            op, sid, kwargs, *_ = self.accepted.get(key) or self.rejected[key]
            _, got = self.run_command(op, f"{sid}-x", kwargs, key, wellformed=False)
            assert got == "IDEMPOTENCY_CONFLICT", f"same key, changed body: {got}"
        elif roll < 0.33:
            digest, journal = self.m.state_digest(), self.m.export_journal()
            try:
                self.m.reject_external(r.choice(("bank-debit", "pg-capture")))
            except SettlementError as error:
                assert error.code == "EXTERNAL_PAYMENT_UNSUPPORTED"
            else:
                raise AssertionError("reject_external returned")
            assert self.m.state_digest() == digest and self.m.export_journal() == journal
        else:
            op, sid = self.pick()
            kwargs, wellformed = self.build(op, sid)
            self.run_command(op, sid, kwargs, self.new_key(), wellformed=wellformed)
        self.check_views()

    def run(self) -> dict:
        for index in range(1, self.steps + 1):
            self.step()
            if index % MACHINE_CHECKPOINT == 0:
                self.check_restore()
        self.check_restore()
        return self.counts


class RefundMachineDriver(MachineDriver):
    """Seeded machine driver biased toward the refund command family.

    Replays prefer the keys of accepted or rejected refund commands, and
    every checkpoint additionally replays the refund keys on a restored
    machine. Everything else (digest/journal atomicity, phase table,
    first-result verbatim replays) is the parent's oracle.
    """

    REFUND_NEXT = {
        None: ("initiate",),
        "INITIATED": ("authorize",) * 9 + ("cancel", "fail"),
        "AUTHORIZED": ("capture",) * 9 + ("cancel", "fail"),
        "CAPTURED": (
            "commit",
            "commit",
            "bind_refund",
            "bind_refund",
            "bind_refund",
            "observe_mock_cancel_acceptance",
        ),
        "COMMITTED": (
            "observe_statement",
            "distribute",
            "bind_refund",
            "bind_refund",
            "bind_refund",
            "observe_mock_cancel_acceptance",
            "observe_mock_cancel_acceptance",
            "reconcile",
        ),
    }

    def __init__(self, seed: int, steps: int = MACHINE_STEPS):
        super().__init__(seed, steps)
        self.bearer: dict = {}

    def pick(self) -> tuple:
        r = self.r
        live = [s for s in SIDS if self.phase(s) not in TERMINAL]
        sid = r.choice(live + list(SIDS) + ["set-ghost"] if r.random() < 0.9 else SIDS)
        phase = self.phase(sid)
        if phase in TERMINAL or r.random() < 0.2:
            op = r.choice(ALL_OPS)
        else:
            op = r.choice(self.REFUND_NEXT[phase])
        return op, sid

    def prefer_key(self, pool: dict) -> str:
        keys = sorted(pool)
        refund_keys = [key for key in keys if pool[key][0] in REFUND_OPS]
        if refund_keys and self.r.random() < 0.75:
            return self.r.choice(refund_keys)
        return self.r.choice(keys)

    def run_command(self, op, sid, kwargs, key, *, wellformed, replay_of=None):
        phase = self.phase(sid)
        result, code = super().run_command(op, sid, kwargs, key, wellformed=wellformed, replay_of=replay_of)
        if result is not None and replay_of is None:
            self.bump(f"ok:{op}@{phase}")
        return result, code

    def check_views(self) -> None:
        super().check_views()
        for sid in SIDS:
            if self.phase(sid) is None:
                continue
            claim = self.m.view(sid)["claim"]
            if claim is None:
                continue
            check_refund_view(claim)
            rank = BEARER_RANK[claim["refund_bearer_policy"]]
            prev = self.bearer.get(sid)
            if prev is not None:
                assert rank == prev or prev == 0, (sid, prev, rank)
            self.bearer[sid] = rank

    def check_restore(self) -> None:
        super().check_restore()
        restored = self.machine_type.restore(self.m.export_journal())
        digest = restored.state_digest()
        for key, (op, sid, kwargs, settlement) in sorted(self.accepted.items()):
            if op not in REFUND_OPS:
                continue
            result = getattr(restored, op)(sid, idempotency_key=key, **kwargs)
            assert result["duplicate"] is True and result["settlement"] == settlement, key
            self.bump("restored-replay:" + op)
        assert restored.state_digest() == digest, "refund-key replays moved the restored machine"

    def step(self) -> None:
        r = self.r
        roll = r.random()
        if roll < 0.15 and self.accepted:
            key = self.prefer_key(self.accepted)
            op, sid, kwargs, settlement = self.accepted[key]
            self.run_command(op, sid, kwargs, key, wellformed=True, replay_of=settlement)
        elif roll < 0.25 and self.rejected:
            key = self.prefer_key(self.rejected)
            op, sid, kwargs, code = self.rejected[key]
            _, got = self.run_command(op, sid, kwargs, key, wellformed=False, replay_of=None)
            assert got == code, f"rejected key replay: {got} != {code}"
        elif roll < 0.33 and (self.accepted or self.rejected):
            pool = {k: self.accepted.get(k) or self.rejected[k] for k in set(self.accepted) | set(self.rejected)}
            key = self.prefer_key(pool)
            op, sid, kwargs, *_ = pool[key]
            _, got = self.run_command(op, f"{sid}-x", kwargs, key, wellformed=False)
            assert got == "IDEMPOTENCY_CONFLICT", f"same key, changed body: {got}"
        elif roll < 0.38:
            digest, journal = self.m.state_digest(), self.m.export_journal()
            try:
                self.m.reject_external(r.choice(("bank-debit", "pg-capture")))
            except SettlementError as error:
                assert error.code == "EXTERNAL_PAYMENT_UNSUPPORTED"
            else:
                raise AssertionError("reject_external returned")
            assert self.m.state_digest() == digest and self.m.export_journal() == journal
        else:
            op, sid = self.pick()
            kwargs, wellformed = self.build(op, sid)
            self.run_command(op, sid, kwargs, self.new_key(), wellformed=wellformed)
        self.check_views()
