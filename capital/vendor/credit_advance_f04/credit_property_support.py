"""Support for the seeded F04 credit property suite. Not a test module.

Author-side harness, builder-authored, not an independent PASS. Fixtures are
synthetic KRW integers, not policy values. No wall clock, no os.urandom, no
network, no files. Seeds are fixed in SEEDS and every random choice comes from
random.Random(seed) over sorted tuples.

Oracles are typed in from docs/contracts/CREDIT_ADVANCE_F04.md sections 1-4 and
7 (option A adopted draft). Nothing is imported from the modules under test
except the objects under test, their exception types and the face provenance
literal. Private tables (_ALLOWED, EXECUTION_KINDS, _REAL_FUNDS,
_UNDEFINED_PRODUCT) are re-typed here, not imported.

The settlement source is a hand-written stub in this support module. It is
test-side. It exposes view() only and never calls a real service.
"""

import json
import random

from credit_fsm import CreditError, CreditMachine
from mock_credit import CreditMockError, MockCredit

SEEDS = (1, 2, 3, 5, 8, 13, 21, 34)
CONTRACT_MONEY_MAX = 10**12

ALWAYS_FALSE_FLAGS = (
    "funds_executed",
    "license_granted",
    "regulated_product",
    "collateral_perfected",
    "priority_bound",
    "disposal_controlled",
    "revenue_assigned",
    "admission_granted",
    "legal_debtor_bound",
    "bank_debit_observed",
    "external_pledge_complete",
    "durable",
    "repayment_observed",
    "interest_defined",
)
MACHINE_FALSE_FIELDS = (
    "economic_finality_claimed",
    "underwriting_executed",
    "kyc_executed",
    "ownership_mutated",
    "ticket_ownership_authoritative",
)
ENVELOPE_FALSE_FIELDS = (
    "economic_finality_claimed",
    "funds_executed",
    "bank_debit_observed",
    "repayment_observed",
    "interest_defined",
    "underwriting_executed",
    "kyc_executed",
)

# Contract section 4 (MOCK_INVARIANT is deliberately absent).
MOCK_CODES = frozenset(
    {
        "INVALID_ID",
        "INVALID_AMOUNT",
        "CURRENCY_UNSUPPORTED",
        "SETTLEMENT_FACE_TYPE",
        "SETTLEMENT_FACE_FIELDS",
        "SETTLEMENT_FACE_NOT_MOCK",
        "SETTLEMENT_FACE_MISMATCH",
        "CREDIT_PRODUCT_UNDEFINED",
        "REAL_FUNDS_FORBIDDEN",
        "REFUND_OBLIGATION_OPEN",
        "FACE_SNAPSHOT_FROZEN",
        "ADVANCE_EXCEEDS_OPEN_FACE",
        "ADVANCE_BINDING_CONFLICT",
        "UNKNOWN_ADVANCE",
        "UNKNOWN_CLAIM",
        "EXECUTION_KIND",
    }
)
# Contract section 7.8 plus the section 7.5 table (UNKNOWN_SETTLEMENT is the
# bound settlement machine's own code).
MACHINE_CODES = MOCK_CODES | frozenset(
    {
        "ILLEGAL_TRANSITION",
        "TERMINAL_IMMUTABLE",
        "IDEMPOTENCY_CONFLICT",
        "INVALID_JOURNAL",
        "DUPLICATE_DRAW",
        "REPAYMENT_ORDER",
        "REPAYMENT_EXCEEDS_OUTSTANDING",
        "REPAY_BINDING_CONFLICT",
        "OUTSTANDING_REMAINS",
        "DEFAULT_REQUIRES_EXPOSURE",
        "SETTLEMENT_SOURCE_REQUIRED",
        "SETTLEMENT_NOT_COMMITTED",
        "SETTLEMENT_AMOUNT_MISMATCH",
        "SETTLEMENT_VIEW_REJECTED",
        "SETTLEMENT_BINDING_CONFLICT",
        "UNKNOWN_SETTLEMENT",
    }
)

# Section 3: attempt_execution table. Section 7.6: reject_unsupported table.
EXECUTION_TABLE = {
    "DISBURSE": "REAL_FUNDS_FORBIDDEN",
    "REPAY": "REAL_FUNDS_FORBIDDEN",
    "DEBIT": "REAL_FUNDS_FORBIDDEN",
    "ACCRUE": "CREDIT_PRODUCT_UNDEFINED",
    "LICENSE": "CREDIT_PRODUCT_UNDEFINED",
    "FORECLOSE": "CREDIT_PRODUCT_UNDEFINED",
    "PRIORITY": "CREDIT_PRODUCT_UNDEFINED",
    "PERFECT": "CREDIT_PRODUCT_UNDEFINED",
}
UNSUPPORTED_TABLE = dict(EXECUTION_TABLE)
UNSUPPORTED_TABLE.update(
    {
        "DISBURSE_TO_BANK": "REAL_FUNDS_FORBIDDEN",
        "INTEREST": "CREDIT_PRODUCT_UNDEFINED",
        "FEE": "CREDIT_PRODUCT_UNDEFINED",
        "KYC": "CREDIT_PRODUCT_UNDEFINED",
        "AML": "CREDIT_PRODUCT_UNDEFINED",
        "KYC_AML": "CREDIT_PRODUCT_UNDEFINED",
        "RISK_SCORE": "CREDIT_PRODUCT_UNDEFINED",
        "UNDERWRITE": "CREDIT_PRODUCT_UNDEFINED",
    }
)
NOT_KINDS = ("", "disburse", "OTHER", "WITHDRAW", "REPAYMENT")

# Section 7.1/7.2 phase table: op -> phases that accept it.
ALLOWED_PHASES = {
    "approve": ("OFFERED",),
    "reject": ("OFFERED",),
    "cancel": ("OFFERED", "APPROVED"),
    "bind_settlement": ("OFFERED", "APPROVED"),
    "draw": ("APPROVED",),
    "repay": ("DRAWN",),
    "close": ("DRAWN",),
    "default": ("DRAWN",),
}
TERMINAL = ("CANCELLED", "CLOSED", "DEFAULTED", "REJECTED")
HOLDING_PHASES = ("DEFAULTED", "DRAWN")  # note stays NOTED and holds ceiling

FALSE_FLAG_KEYS = (
    "legal_debtor_bound",
    "admission_granted",
    "right_cancelled",
    "bank_debit_observed",
    "external_return_closed",
    "funds_executed",
)


def rng(seed):
    return random.Random(seed)


def canon(value):
    return json.dumps(value, sort_keys=True, ensure_ascii=False, separators=(",", ":"))


def code_of(fn, error=CreditError):
    try:
        fn()
    except error as caught:
        return caught.code
    raise AssertionError("expected an error")


def mock_code_of(fn):
    return code_of(fn, CreditMockError)


# ---- faces -----------------------------------------------------------------


def make_face(claim_id, faces, dists, variant, cash=None, recovery=None, refund=1):
    """Return (face dict, oracle open_face). open_face is re-derived here."""
    gross = sum(faces)
    lines = []
    open_face = 0
    for index, (face, dist) in enumerate(zip(faces, dists)):
        cancelled = 0
        if variant == "reclass":
            cancelled = face - dist
        outstanding = face - dist - cancelled
        open_face += outstanding
        lines.append(
            {
                "payee": "payee-%d" % index,
                "face": face,
                "distributed": dist,
                "cancelled_unpaid": cancelled,
                "outstanding": outstanding,
            }
        )
    refund_face = 0
    bearer = "NONE"
    if variant == "reclass":
        refund_face, bearer = gross, "FIXTURE_FULL_GROSS_RECLASS"
    elif variant == "open-refund":
        refund_face, bearer = min(refund, gross), "REQUESTER"
    face = {
        "provenance": "MOCK_SETTLEMENT_ONLY",
        "claim_id": claim_id,
        "trade_id": "trade-" + claim_id,
        "currency": "KRW",
        "gross": gross,
        "obligations": lines,
        "refund_face": refund_face,
        "fixture_reclassified": variant == "reclass",
        "refund_bearer_policy": bearer,
        "confirmed_cash": min(gross, CONTRACT_MONEY_MAX) if cash is None else cash,
        "recovery_due": min(gross, CONTRACT_MONEY_MAX) if recovery is None else recovery,
    }
    for name in FALSE_FLAG_KEYS:
        face[name] = False
    return face, open_face


FACE_DEFECTS = {
    "provenance": ("SETTLEMENT_FACE_NOT_MOCK", lambda f: f.update(provenance="OTHER")),
    "flag": ("SETTLEMENT_FACE_NOT_MOCK", lambda f: f.update(bank_debit_observed=True)),
    "currency": ("CURRENCY_UNSUPPORTED", lambda f: f.update(currency="USD")),
    "gross": ("SETTLEMENT_FACE_MISMATCH", lambda f: f.update(gross=f["gross"] + 1)),
    "stated": (
        "SETTLEMENT_FACE_MISMATCH",
        lambda f: f["obligations"][0].update(outstanding=f["obligations"][0]["outstanding"] + 1),
    ),
    "fields": ("SETTLEMENT_FACE_FIELDS", lambda f: f.pop("recovery_due")),
    "type": ("SETTLEMENT_FACE_TYPE", None),
}


def defective(face, name):
    code, mutate = FACE_DEFECTS[name]
    if mutate is None:
        return ["not", "a", "face"], code
    copy = json.loads(canon(face))
    mutate(copy)
    return copy, code


# ---- settlement stub -------------------------------------------------------

PHASE_ORDER = ("INITIATED", "AUTHORIZED", "CAPTURED", "COMMITTED")
STUB_KINDS = ("bank-debit-flag", "failed", "finality-flag", "gross-mismatch", "ok", "wrong-claim")


class StubUnknown(Exception):
    code = "UNKNOWN_SETTLEMENT"


class StubSettlementSource:
    """Hand-written settlement view source. view() only, forward-only phases."""

    def __init__(self):
        self._rows = {}
        self.reads = 0

    def register(self, settlement_id, kind, claim_id, gross):
        assert kind in STUB_KINDS
        phase = "INITIATED" if kind == "ok" else ("FAILED" if kind == "failed" else "COMMITTED")
        self._rows[settlement_id] = {"kind": kind, "claim_id": claim_id, "gross": gross, "phase": phase}

    def ids(self):
        return tuple(sorted(self._rows))

    def tick(self, settlement_id):
        row = self._rows[settlement_id]
        if row["kind"] == "ok" and row["phase"] != "COMMITTED":
            row["phase"] = PHASE_ORDER[PHASE_ORDER.index(row["phase"]) + 1]

    def snapshot(self):
        return canon(self._rows)

    def peek(self, settlement_id):
        row = self._rows.get(settlement_id)
        if row is None:
            raise StubUnknown("UNKNOWN_SETTLEMENT")
        view = {
            "settlement_id": "other-claim" if row["kind"] == "wrong-claim" else row["claim_id"],
            "phase": row["phase"],
            "currency": "KRW",
            "gross": row["gross"] + 1 if row["kind"] == "gross-mismatch" else row["gross"],
            "economic_finality_claimed": row["kind"] == "finality-flag",
            "funds_executed": False,
            "bank_debit_observed": False,
            "legal_debtor_bound": False,
            "admission_granted": False,
            "durable": False,
            "claim": {
                "provenance": "MOCK_SETTLEMENT_ONLY",
                "claim_id": row["claim_id"],
                "currency": "KRW",
                "gross": row["gross"],
                "funds_executed": False,
                "bank_debit_observed": row["kind"] == "bank-debit-flag",
            },
        }
        return view

    def view(self, settlement_id):
        self.reads += 1
        return self.peek(settlement_id)


def oracle_gate(view, claim_id, gross):
    """Section 7.5: every violated condition of a bound draw's settlement view."""
    codes = set()
    if view["phase"] != "COMMITTED":
        codes.add("SETTLEMENT_NOT_COMMITTED")
    if view["settlement_id"] != claim_id or view["claim"]["claim_id"] != claim_id:
        codes.add("SETTLEMENT_BINDING_CONFLICT")
    if view["currency"] != "KRW" or view["gross"] != gross or view["claim"]["gross"] != gross:
        codes.add("SETTLEMENT_AMOUNT_MISMATCH")
    if (
        view["economic_finality_claimed"]
        or view["funds_executed"]
        or view["bank_debit_observed"]
        or view["claim"]["bank_debit_observed"]
        or view["claim"]["funds_executed"]
    ):
        codes.add("SETTLEMENT_VIEW_REJECTED")
    return codes


def expected_gate(stub, settlement_id, claim_id, gross):
    try:
        view = stub.peek(settlement_id)
    except StubUnknown:
        return {"UNKNOWN_SETTLEMENT"}
    return oracle_gate(view, claim_id, gross)


# ---- claim fixtures --------------------------------------------------------

CLAIM_SHAPES = (
    ("claim-a", (60_000, 30_000)),
    ("claim-b", (CONTRACT_MONEY_MAX - 7, 7)),
    ("claim-c", (4, 3)),
)
VARIANTS = ("later", "open-refund", "plain", "plain", "plain", "plain", "plain", "reclass")


def claim_faces(r, claim_id, faces):
    """Base face plus labelled variants for one claim. Cash is made large."""
    gross = sum(faces)
    base = [r.randint(0, value) for value in faces]
    later = [min(value, dist + r.randint(0, value - dist)) for value, dist in zip(faces, base)]
    plain_cash, plain_recovery = min(gross // 2 + 1, CONTRACT_MONEY_MAX), gross
    return {
        "plain": make_face(claim_id, faces, base, "plain", plain_cash, plain_recovery),
        # later settlement: more distributed (when room), more cash, other recovery_due
        "later": make_face(claim_id, faces, later, "later", gross, gross - 1),
        "open-refund": make_face(claim_id, faces, base, "open-refund", plain_cash, plain_recovery,
                                 refund=r.randint(1, gross)),
        "reclass": make_face(claim_id, faces, base, "reclass", plain_cash, plain_recovery),
    }


def amount_candidates(open_face, reserved):
    raw = {1, open_face, open_face // 2, open_face // 3, open_face - reserved, open_face - reserved + 1,
           open_face - reserved - 1, reserved + 1}
    return tuple(sorted(value for value in raw if 1 <= value <= CONTRACT_MONEY_MAX))


# ---- shared view checks ----------------------------------------------------


def check_flags(view, names, label):
    for name in names:
        if name in view and view[name] is not False:
            raise AssertionError("%s: %s is not False" % (label, name))


def check_terms(view):
    terms = view["open_terms"]
    if terms.get("decided_value") is not None or terms.get("adopted_option") != "A":
        raise AssertionError("open_terms moved off the adopted unfilled boundary")
    if terms.get("policy_number_status") != "UNDETERMINED" or "apr_bps" in terms or "schedule" in terms:
        raise AssertionError("open_terms carries a policy value")


def nonneg_int(view, names, label):
    for name in names:
        value = view[name]
        if type(value) is not int or value < 0 or value > CONTRACT_MONEY_MAX:
            raise AssertionError("%s: %s=%r is not a bounded non-negative integer" % (label, name, value))


def check_claim_numbers(view, label):
    nonneg_int(view, ("open_face", "reserved_open", "residual_unreserved", "confirmed_cash_on_face",
                      "recovery_due_on_face"), label)
    if view["reserved_open"] > view["open_face"]:
        raise AssertionError("%s: reserved_open exceeds open_face" % label)
    if view["residual_unreserved"] != view["open_face"] - view["reserved_open"]:
        raise AssertionError("%s: residual_unreserved is not open_face - reserved_open" % label)


# ---- MockCredit driver -----------------------------------------------------


class MockDriver:
    """Seeded sequences against MockCredit with a contract-ordered oracle."""

    def __init__(self, seed):
        self.r = rng(seed)
        self.mock = MockCredit()
        self.faces = {}
        self.claims = {}  # claim_id -> {"canon", "open_face", "cash", "recovery"}
        self.adv = {}  # advance_id -> model row
        self.counters = {}
        self.codes = set()
        self.specs = []
        for index in range(10):
            claim_id, faces = CLAIM_SHAPES[index % len(CLAIM_SHAPES)]
            if claim_id not in self.faces:
                self.faces[claim_id] = claim_faces(self.r, claim_id, faces)
            variant = self.r.choice(VARIANTS)
            face, open_face = self.faces[claim_id][variant]
            amount = self.r.choice(amount_candidates(max(open_face, 1), 0))
            self.specs.append(
                {"id": "adv-%d" % index, "claim": claim_id, "variant": variant, "face": face,
                 "open_face": open_face, "amount": amount, "role": "role-%d" % (index % 3)}
            )

    # model ------------------------------------------------------------
    def reserved(self, claim_id):
        return sum(row["amount"] for row in self.adv.values() if row["claim"] == claim_id and row["status"] == "NOTED")

    def bump(self, name):
        self.counters[name] = self.counters.get(name, 0) + 1

    def expect_note(self, spec, face, amount, role, product, advance_id, face_code=None):
        """Section 3 order of checks. Returns a code, 'dup' or None."""
        if product is not None:
            return "CREDIT_PRODUCT_UNDEFINED"
        if type(advance_id) is not str or not advance_id or advance_id.strip() != advance_id or len(advance_id) > 100:
            return "INVALID_ID"
        if type(amount) is not int or not 0 < amount <= CONTRACT_MONEY_MAX:
            return "INVALID_AMOUNT"
        if face_code:
            return face_code
        known = self.adv.get(advance_id)
        if known is not None:
            same = (known["amount"], known["role"], canon(known["face"])) == (amount, role, canon(face))
            return "dup" if same else "ADVANCE_BINDING_CONFLICT"
        if spec["variant"] == "open-refund":
            return "REFUND_OBLIGATION_OPEN"
        claim = self.claims.get(spec["claim"])
        open_face = spec["open_face"]
        if claim is not None:
            if claim["canon"] != canon(face):
                return "FACE_SNAPSHOT_FROZEN"
            open_face = claim["open_face"]
        if amount > open_face - self.reserved(spec["claim"]):
            return "ADVANCE_EXCEEDS_OPEN_FACE"
        return None

    # snapshots --------------------------------------------------------
    def snapshot(self):
        views = {}
        for advance_id in sorted(self.adv):
            views[advance_id] = self.mock.view(advance_id)
        for claim_id in sorted(self.claims):
            views["claim:" + claim_id] = self.mock.view_claim(claim_id)
        return canon(views)

    def attempt(self, fn):
        try:
            return fn(), None
        except CreditMockError as error:
            return None, error.code

    # steps ------------------------------------------------------------
    def run(self, steps):
        for _ in range(steps):
            self.step()
            self.check()
        return self.counters

    def step(self):
        r = self.r
        spec = r.choice(self.specs)
        choice = r.choice(("note", "note", "note", "note", "release", "release", "execute", "unknown", "mutate"))
        before = self.snapshot()
        if choice == "note":
            self.do_note(spec, before)
        elif choice == "mutate":
            self.do_mutated_note(spec, before)
        elif choice == "release":
            self.do_release(spec["id"], before)
        elif choice == "execute":
            self.do_execute(spec["id"], before)
        else:
            self.do_unknown(before)

    def do_note(self, spec, before, amount=None, role=None, face=None):
        face = spec["face"] if face is None else face
        if amount is None:
            claim = self.claims.get(spec["claim"])
            open_face = spec["open_face"] if claim is None else claim["open_face"]
            amount = self.r.choice(amount_candidates(max(open_face, 1), self.reserved(spec["claim"])))
        role = spec["role"] if role is None else role
        expected = self.expect_note(spec, face, amount, role, None, spec["id"])
        got, code = self.attempt(
            lambda: self.mock.note_advance(spec["id"], face=face, amount=amount, beneficiary_role=role)
        )
        self.finish("note_advance", expected, got, code, before)
        if expected is None:
            self.adv[spec["id"]] = {"claim": spec["claim"], "amount": amount, "role": role,
                                    "face": face, "status": "NOTED"}
            if spec["claim"] not in self.claims:
                self.claims[spec["claim"]] = {
                    "canon": canon(face), "open_face": spec["open_face"],
                    "cash": face["confirmed_cash"], "recovery": face["recovery_due"],
                }

    def do_mutated_note(self, spec, before):
        r = self.r
        kind = r.choice(("product", "id", "amount-zero", "amount-big", "amount-bool", "face", "face", "conflict"))
        advance_id = spec["id"]
        face, amount, role, product, face_code = spec["face"], spec["amount"], spec["role"], None, None
        if kind == "product":
            product = r.choice(({}, "loan", {"apr": 1}))
        elif kind == "id":
            advance_id = r.choice(("", " adv", "adv ", "x" * 101, 7))
        elif kind == "amount-zero":
            amount = 0
        elif kind == "amount-big":
            amount = CONTRACT_MONEY_MAX + 1
        elif kind == "amount-bool":
            amount = True
        elif kind == "face":
            face, face_code = defective(face, r.choice(sorted(FACE_DEFECTS)))
        else:
            known = [row for row in self.adv.items()]
            if not known:
                return
            advance_id, row = r.choice(known)
            spec = next(s for s in self.specs if s["id"] == advance_id)
            face = row["face"]
            amount = row["amount"] + 1 if r.random() < 0.5 else row["amount"]
            role = row["role"] if amount != row["amount"] else row["role"] + "-x"
        expected = self.expect_note(spec, face, amount, role, product, advance_id, face_code)
        kwargs = {"face": face, "amount": amount, "beneficiary_role": role}
        if product is not None:
            kwargs["product"] = product
        got, code = self.attempt(lambda: self.mock.note_advance(advance_id, **kwargs))
        if expected == "dup":
            raise AssertionError("mutation produced a duplicate")
        self.finish("note_advance", expected, got, code, before)

    def do_release(self, advance_id, before):
        row = self.adv.get(advance_id)
        expected = "UNKNOWN_ADVANCE" if row is None else ("dup" if row["status"] == "RELEASED" else None)
        reserved_before = None if row is None else self.reserved(row["claim"])
        got, code = self.attempt(lambda: self.mock.release_note(advance_id))
        self.finish("release_note", expected, got, code, before)
        if expected is None:
            row["status"] = "RELEASED"
            claim = self.mock.view_claim(row["claim"])
            if claim["reserved_open"] != reserved_before - row["amount"]:
                raise AssertionError("release did not return exactly the noted amount")
            if got["advance"]["repayment_observed"] is not False:
                raise AssertionError("release was reported as a repayment")

    def do_execute(self, advance_id, before):
        r = self.r
        kind = r.choice(sorted(EXECUTION_TABLE) + list(NOT_KINDS))
        if kind not in EXECUTION_TABLE:
            expected = "EXECUTION_KIND"
        elif advance_id not in self.adv:
            expected = "UNKNOWN_ADVANCE"
        else:
            expected = EXECUTION_TABLE[kind]
        got, code = self.attempt(lambda: self.mock.attempt_execution(advance_id, kind=kind))
        if got is not None or code != expected:
            raise AssertionError("attempt_execution %r gave %r, expected %r" % (kind, code, expected))
        if self.snapshot() != before:
            raise AssertionError("attempt_execution changed a view")
        self.codes.add(code)
        self.bump("execute")

    def do_unknown(self, before):
        for fn, expected in ((lambda: self.mock.view("nope"), "UNKNOWN_ADVANCE"),
                             (lambda: self.mock.view_claim("claim-none"), "UNKNOWN_CLAIM"),
                             (lambda: self.mock.release_note("nope"), "UNKNOWN_ADVANCE")):
            if mock_code_of(fn) != expected:
                raise AssertionError("unknown id gave the wrong code")
        if self.snapshot() != before:
            raise AssertionError("an unknown lookup changed a view")
        self.bump("unknown")

    def finish(self, name, expected, got, code, before):
        if expected is None or expected == "dup":
            if code is not None:
                raise AssertionError("%s rejected with %s, expected success" % (name, code))
            if got["duplicate"] is not (expected == "dup"):
                raise AssertionError("%s duplicate flag wrong" % name)
            if got["applied"] is not None:
                raise AssertionError("applied must be None")
            if expected == "dup" and self.snapshot() != before:
                raise AssertionError("a duplicate changed a view")
            self.bump(name + (":dup" if expected == "dup" else ":ok"))
        else:
            if got is not None:
                raise AssertionError("%s accepted but the contract says %s" % (name, expected))
            if code != expected:
                raise AssertionError("%s raised %s, expected %s" % (name, code, expected))
            if code not in MOCK_CODES:
                raise AssertionError("code %s is not in contract section 4" % code)
            if self.snapshot() != before:
                raise AssertionError("a rejected %s changed a view" % name)
            self.codes.add(code)
            self.bump(name + ":" + code)

    def check(self):
        for claim_id, claim in sorted(self.claims.items()):
            view = self.mock.view_claim(claim_id)
            check_claim_numbers(view, claim_id)
            check_flags(view, ALWAYS_FALSE_FLAGS, claim_id)
            check_terms(view)
            if view["open_face"] != claim["open_face"]:
                raise AssertionError("%s: open_face is not the frozen unpaid face" % claim_id)
            if view["reserved_open"] != self.reserved(claim_id):
                raise AssertionError("%s: reserved_open is not the sum of NOTED amounts" % claim_id)
            if view["confirmed_cash_on_face"] != claim["cash"] or view["recovery_due_on_face"] != claim["recovery"]:
                raise AssertionError("%s: cash or recovery_due changed" % claim_id)
            if self.reserved(claim_id) > claim["open_face"]:
                raise AssertionError("%s: reservations exceed the claim's unpaid face" % claim_id)
            if view["snapshot_frozen"] is not True:
                raise AssertionError("snapshot_frozen must stay true")
        for advance_id, row in sorted(self.adv.items()):
            view = self.mock.view(advance_id)
            check_claim_numbers(view, advance_id)
            if view["status"] != row["status"] or view["amount"] != row["amount"]:
                raise AssertionError("%s: status or amount drifted" % advance_id)
        for claim_id in sorted(set(CLAIM_SHAPES[i][0] for i in range(3)) - set(self.claims)):
            if mock_code_of(lambda: self.mock.view_claim(claim_id)) != "UNKNOWN_CLAIM":
                raise AssertionError("a never-noted claim must be UNKNOWN_CLAIM")


# ---- CreditMachine driver --------------------------------------------------

ALL_OPS = ("offer", "approve", "reject", "cancel", "bind_settlement", "draw", "repay", "close", "default",
           "reconcile", "unsupported", "execution", "replay", "conflict", "tick")
VALID_OPS = {
    None: ("offer",),
    "OFFERED": ("approve",) * 6 + ("bind_settlement", "bind_settlement", "reject", "cancel"),
    "APPROVED": ("bind_settlement", "draw", "draw", "draw", "draw", "draw", "tick", "cancel"),
    "DRAWN": ("repay",) * 6 + ("close", "default", "reconcile"),
    "CLOSED": ("repay", "draw", "approve", "bind_settlement", "close", "reconcile"),
    "DEFAULTED": ("repay", "close", "default", "draw", "reconcile"),
    "REJECTED": ("approve", "draw", "cancel", "bind_settlement"),
    "CANCELLED": ("draw", "approve", "reject", "offer"),
}
REPLAYABLE_OPS = ("offer", "approve", "reject", "cancel", "bind_settlement", "draw", "repay", "close", "default")
STUB_SUFFIX = {"ok": "ok", "failed": "failed", "wrong-claim": "wrong", "gross-mismatch": "gross",
               "finality-flag": "final", "bank-debit-flag": "bank"}


class Case:
    def __init__(self, spec, amount, role, face):
        self.spec, self.amount, self.role, self.face = spec, amount, role, face
        self.phase = "OFFERED"
        self.sid = None
        self.draw_id = None
        self.repays = {}
        self.order = []
        self.outstanding = 0
        self.repaid = 0
        self.gate_observed = False


class MachineDriver:
    def __init__(self, seed):
        self.r = rng(seed)
        self.stub = StubSettlementSource()
        self.m = CreditMachine(self.stub)
        self.faces = {}
        for claim_id, faces in CLAIM_SHAPES:
            self.faces[claim_id] = claim_faces(self.r, claim_id, faces)
            gross = sum(faces)
            for kind in STUB_KINDS:
                self.stub.register("st-%s-%s" % (claim_id, STUB_SUFFIX[kind]), kind, claim_id, gross)
        self.sids = self.stub.ids() + ("st-unregistered",)
        self.specs = []
        for index in range(9):
            claim_id, faces = CLAIM_SHAPES[index % 3]
            variant = self.r.choice(VARIANTS)
            face, open_face = self.faces[claim_id][variant]
            amount = self.r.choice(amount_candidates(max(open_face, 1), 0))
            self.specs.append({"id": "adv-%d" % index, "claim": claim_id, "variant": variant, "face": face,
                               "open_face": open_face, "amount": amount, "role": "role-%d" % (index % 3),
                               "gross": sum(faces)})
        self.cases = {}
        self.frozen = {}  # claim_id -> {"canon", "open_face", "cash", "recovery"}
        self.history = {}  # key -> (op, adv, kwargs, result or error code)
        self.digests = {}
        self.counters = {}
        self.codes = set()
        self.keys = 0
        self.digests[0] = self.m.state_digest()

    # model ------------------------------------------------------------
    def bump(self, name):
        self.counters[name] = self.counters.get(name, 0) + 1

    def key(self):
        self.keys += 1
        return "k-%d" % self.keys

    def reserved(self, claim_id):
        return sum(c.amount for c in self.cases.values() if c.spec["claim"] == claim_id and c.phase in HOLDING_PHASES)

    def phase_code(self, case, op):
        if case.phase in ALLOWED_PHASES[op]:
            return None
        return "TERMINAL_IMMUTABLE" if case.phase in TERMINAL else "ILLEGAL_TRANSITION"

    # call plumbing ----------------------------------------------------
    def state(self):
        return self.m.state_digest(), canon(self.m.export_journal()), self.stub.snapshot(), self.stub.reads

    def call(self, op, advance_id, key, kwargs, expect, remember=True):
        """expect is ('ok',), ('dup',) or ('err', set_of_codes)."""
        digest, journal, stub_state, reads = self.state()
        entries = len(self.m.export_journal())
        try:
            result, code = getattr(self.m, op)(advance_id, idempotency_key=key, **kwargs), None
        except CreditError as error:
            result, code = None, error.code
        except Exception as error:  # an unexpected exception type is itself a failure
            raise AssertionError("%s raised %r" % (op, error))
        after_digest, after_journal, after_stub, after_reads = self.state()
        if after_stub != stub_state:
            raise AssertionError("%s changed the settlement source" % op)
        if op not in ("draw", "reconcile") and after_reads != reads:
            raise AssertionError("%s read the settlement source" % op)
        if code is not None:
            if expect[0] != "err" or code not in expect[1]:
                raise AssertionError("%s raised %s, expected %r" % (op, code, expect))
            if code not in MACHINE_CODES:
                raise AssertionError("code %s is outside the contract tables" % code)
            if (after_digest, after_journal) != (digest, journal):
                raise AssertionError("a rejected %s changed state_digest or the journal" % op)
            self.codes.add(code)
            self.bump("%s:%s" % (op, code))
            if remember and code != "INVALID_ID":
                self.history[key] = (op, advance_id, kwargs, code)
            return None
        if expect[0] == "err":
            raise AssertionError("%s was accepted but violates %r" % (op, expect[1]))
        for name in ENVELOPE_FALSE_FIELDS:
            if result[name] is not False:
                raise AssertionError("%s result %s is not False" % (op, name))
        grown = len(self.m.export_journal()) - entries
        if expect[0] == "dup":
            if result["duplicate"] is not True or result["applied"] is not None or grown != 0:
                raise AssertionError("%s duplicate was not inert" % op)
            if after_digest != digest:
                raise AssertionError("a duplicate %s changed state_digest" % op)
            self.bump(op + ":dup")
        else:
            if result["duplicate"] is not False:
                raise AssertionError("%s first result flagged duplicate" % op)
            want_applied = op
            if result["applied"] != want_applied:
                raise AssertionError("%s applied=%r" % (op, result["applied"]))
            if op == "reconcile":
                if grown != 0 or after_digest != digest or result["matched"] is not True:
                    raise AssertionError("reconcile moved state or did not match")
                if result["state_digest"] != digest or result["entry_count"] != entries:
                    raise AssertionError("reconcile reported another digest or count")
            else:
                if grown != 1:
                    raise AssertionError("%s: journal grew by %d" % (op, grown))
                entry = self.m.export_journal()[-1]
                if entry["op"] != op or entry["advance_id"] != advance_id or entry["idempotency_key"] != key:
                    raise AssertionError("%s: last journal entry is not this command" % op)
                self.digests[entries + 1] = after_digest
            self.bump(op + ":ok")
        if remember:
            self.history[key] = (op, advance_id, kwargs, result)
        return result

    # steps ------------------------------------------------------------
    def run(self, steps, restore_every=10):
        for index in range(steps):
            self.step()
            self.check()
            if restore_every and index % restore_every == restore_every - 1:
                self.check_restore()
        self.check_restore()
        return self.counters

    def check_restore(self):
        restored = CreditMachine.restore(self.m.export_journal(), settlement_source=self.stub)
        if restored.state_digest() != self.m.state_digest() or restored.canonical_state() != self.m.canonical_state():
            raise AssertionError("restore(export_journal()) differs from the live machine")

    def check_prefixes(self):
        journal = self.m.export_journal()
        for k in range(len(journal) + 1):
            if CreditMachine.restore(journal[:k], settlement_source=self.stub).state_digest() != self.digests[k]:
                raise AssertionError("restore of journal prefix %d differs from the live digest" % k)
        self.bump("prefixes")

    def step(self):
        r = self.r
        spec = r.choice(self.specs)
        case = self.cases.get(spec["id"])
        phase = case.phase if case else None
        op = r.choice(VALID_OPS[phase]) if r.random() < 0.8 else r.choice(ALL_OPS)
        getattr(self, "do_" + op)(spec["id"], spec)

    def reason(self):
        return ("", "why") [self.r.random() < 0.9]

    def do_offer(self, advance_id, spec):
        r = self.r
        face, amount, role, product, defect = spec["face"], spec["amount"], spec["role"], None, None
        case = self.cases.get(advance_id)
        mode = r.choice(("ok", "ok", "ok", "product", "face", "amount", "binding"))
        kwargs_id = advance_id
        if mode == "product":
            product = r.choice(({}, "loan"))
        elif mode == "face":
            face, defect = defective(face, r.choice(sorted(FACE_DEFECTS)))
        elif mode == "amount":
            amount = r.choice((0, CONTRACT_MONEY_MAX + 1, True))
        elif mode == "binding":
            amount = amount + 1 if amount < CONTRACT_MONEY_MAX else amount - 1
        kwargs = {"face": face, "amount": amount, "beneficiary_role": role}
        if product is not None:
            kwargs["product"] = product
        if product is not None:
            expect = ("err", {"CREDIT_PRODUCT_UNDEFINED"})
        elif defect or type(amount) is not int or not 0 < amount <= CONTRACT_MONEY_MAX:
            code = defect or "INVALID_AMOUNT"
            expect = ("err", {code})
        elif spec["variant"] == "open-refund":
            expect = ("err", {"REFUND_OBLIGATION_OPEN"})
        elif case is not None:
            same = (amount, role, canon(face)) == (case.amount, case.role, canon(case.face))
            expect = ("err", {"ILLEGAL_TRANSITION" if same else "ADVANCE_BINDING_CONFLICT"})
        else:
            expect = ("ok",)
        if self.call("offer", kwargs_id, self.key(), kwargs, expect) is not None:
            self.cases[advance_id] = Case(spec, amount, role, face)

    def simple(self, op, advance_id, extra=None, bad=False):
        case = self.cases.get(advance_id)
        kwargs = dict(extra or {})
        codes = set()
        if case is None:
            codes.add("UNKNOWN_ADVANCE")
        else:
            if bad:
                codes.add("INVALID_ID")
            phase_code = self.phase_code(case, op)
            if phase_code:
                codes.add(phase_code)
        return case, kwargs, (("err", codes) if codes else ("ok",))

    def do_approve(self, advance_id, spec):
        case, kwargs, expect = self.simple("approve", advance_id)
        if self.call("approve", advance_id, self.key(), kwargs, expect) is not None:
            case.phase = "APPROVED"

    def do_reject(self, advance_id, spec):
        reason = self.reason()
        case, kwargs, expect = self.simple("reject", advance_id, {"reason": reason}, reason == "")
        if self.call("reject", advance_id, self.key(), kwargs, expect) is not None:
            case.phase = "REJECTED"

    def do_cancel(self, advance_id, spec):
        reason = self.reason()
        case, kwargs, expect = self.simple("cancel", advance_id, {"reason": reason}, reason == "")
        if self.call("cancel", advance_id, self.key(), kwargs, expect) is not None:
            case.phase = "CANCELLED"

    def do_bind_settlement(self, advance_id, spec):
        sid = self.r.choice(self.sids + ("",))
        case, kwargs, expect = self.simple("bind_settlement", advance_id, {"settlement_id": sid}, sid == "")
        if case is not None and sid != "" and case.sid is not None and self.phase_code(case, "bind_settlement") is None:
            expect = ("err", {"ILLEGAL_TRANSITION" if case.sid == sid else "SETTLEMENT_BINDING_CONFLICT"})
        if self.call("bind_settlement", advance_id, self.key(), kwargs, expect) is not None:
            case.sid = sid

    def do_draw(self, advance_id, spec):
        r = self.r
        case = self.cases.get(advance_id)
        draw_id = "dr-" + advance_id
        if case is not None and case.draw_id is not None and r.random() < 0.5:
            draw_id = "dr-other"
        if r.random() < 0.06:
            draw_id = ""
        kwargs = {"draw_id": draw_id}
        if case is None:
            expect = ("err", {"UNKNOWN_ADVANCE"})
        elif draw_id == "":
            expect = ("err", {"INVALID_ID"})
        elif case.draw_id is not None:
            if case.draw_id == draw_id:
                expect = ("dup",)
            else:
                expect = ("err", {"TERMINAL_IMMUTABLE" if case.phase in TERMINAL else "DUPLICATE_DRAW"})
        elif case.phase != "APPROVED":
            expect = ("err", {self.phase_code(case, "draw")})
        else:
            expect = self.draw_expectation(case)
        result = self.call("draw", advance_id, self.key(), kwargs, expect)
        if result is not None and expect[0] == "ok":
            self.accept_draw(case, draw_id)

    def draw_expectation(self, case):
        claim_id = case.spec["claim"]
        if case.sid is not None:
            gate = expected_gate(self.stub, case.sid, claim_id, case.spec["gross"])
            if gate:
                return ("err", gate)
        frozen = self.frozen.get(claim_id)
        open_face = case.spec["open_face"]
        if frozen is not None:
            if frozen["canon"] != canon(case.face):
                return ("err", {"FACE_SNAPSHOT_FROZEN"})
            open_face = frozen["open_face"]
        if case.amount > open_face - self.reserved(claim_id):
            return ("err", {"ADVANCE_EXCEEDS_OPEN_FACE"})
        return ("ok",)

    def accept_draw(self, case, draw_id):
        claim_id = case.spec["claim"]
        case.phase, case.draw_id, case.outstanding = "DRAWN", draw_id, case.amount
        case.gate_observed = case.sid is not None
        if claim_id not in self.frozen:
            self.frozen[claim_id] = {"canon": canon(case.face), "open_face": case.spec["open_face"],
                                     "cash": case.face["confirmed_cash"], "recovery": case.face["recovery_due"]}

    def do_repay(self, advance_id, spec):
        r = self.r
        case = self.cases.get(advance_id)
        mode = r.choice(("ok", "ok", "ok", "ok", "again", "changed", "order", "over", "zero"))
        outstanding = 0 if case is None else case.outstanding
        repay_id = "rp-%d" % (self.keys + 1)
        seq = 1 if case is None else len(case.order) + 1
        amount = r.randint(1, max(outstanding, 1))
        if case is not None and case.repays and mode in ("again", "changed"):
            repay_id = r.choice(sorted(case.repays))
            seq, amount = case.repays[repay_id]
            if mode == "changed":
                amount = amount + 1 if amount < CONTRACT_MONEY_MAX else amount - 1
        elif mode == "order":
            seq = r.choice((0, seq + 1, True))
        elif mode == "over":
            amount = outstanding + 1
        elif mode == "zero":
            amount = r.choice((0, -1))
        kwargs = {"repay_id": repay_id, "sequence": seq, "amount": amount}
        if case is None:
            expect = ("err", {"UNKNOWN_ADVANCE"})
        else:
            expect = self.repay_expectation(case, repay_id, seq, amount)
        result = self.call("repay", advance_id, self.key(), kwargs, expect)
        if result is not None and expect[0] == "ok":
            case.repays[repay_id] = (seq, amount)
            case.order.append(amount)
            case.repaid += amount
            case.outstanding -= amount

    def repay_expectation(self, case, repay_id, seq, amount):
        invalid = set()
        if type(amount) is not int or not 0 < amount <= CONTRACT_MONEY_MAX:
            invalid.add("INVALID_AMOUNT")
        if type(seq) is not int or seq < 1:
            invalid.add("REPAYMENT_ORDER")
        if invalid:
            return ("err", invalid)
        prior = case.repays.get(repay_id)
        if prior is not None:
            return ("dup",) if prior == (seq, amount) else ("err", {"REPAY_BINDING_CONFLICT"})
        phase_code = self.phase_code(case, "repay")
        if phase_code:
            return ("err", {phase_code})
        codes = set()
        if seq != len(case.order) + 1:
            codes.add("REPAYMENT_ORDER")
        if amount > case.outstanding:
            codes.add("REPAYMENT_EXCEEDS_OUTSTANDING")
        return ("err", codes) if codes else ("ok",)

    def do_close(self, advance_id, spec):
        case, kwargs, expect = self.simple("close", advance_id)
        if case is not None and expect[0] == "ok" and case.outstanding > 0:
            expect = ("err", {"OUTSTANDING_REMAINS"})
        if self.call("close", advance_id, self.key(), kwargs, expect) is not None:
            case.phase = "CLOSED"

    def do_default(self, advance_id, spec):
        reason = self.reason()
        case, kwargs, expect = self.simple("default", advance_id, {"reason": reason}, reason == "")
        if case is not None and expect[0] == "ok" and case.outstanding == 0:
            expect = ("err", {"DEFAULT_REQUIRES_EXPOSURE"})
        if self.call("default", advance_id, self.key(), kwargs, expect) is not None:
            case.phase = "DEFAULTED"

    def do_reconcile(self, advance_id, spec):
        expect = ("ok",) if advance_id in self.cases else ("err", {"UNKNOWN_ADVANCE"})
        self.call("reconcile", advance_id, self.key(), {}, expect)

    def do_unsupported(self, advance_id, spec):
        kind = self.r.choice(sorted(UNSUPPORTED_TABLE) + list(NOT_KINDS))
        expected = UNSUPPORTED_TABLE.get(kind, "EXECUTION_KIND")
        before = self.state()
        code = code_of(lambda: self.m.reject_unsupported(kind))
        if code != expected or self.state() != before:
            raise AssertionError("reject_unsupported(%r) gave %s or changed state" % (kind, code))
        self.codes.add(code)
        self.bump("unsupported")

    def do_execution(self, advance_id, spec):
        kind = self.r.choice(sorted(EXECUTION_TABLE) + list(NOT_KINDS))
        case = self.cases.get(advance_id)
        if kind not in EXECUTION_TABLE:
            expected = "EXECUTION_KIND"
        elif case is None or case.phase not in ("DRAWN", "DEFAULTED", "CLOSED"):
            expected = "UNKNOWN_ADVANCE"  # section 3: no note, no refusal code
        else:
            expected = EXECUTION_TABLE[kind]
        before = self.state()
        code = code_of(lambda: self.m.attempt_execution(advance_id, kind=kind))
        if code != expected or self.state() != before:
            raise AssertionError("attempt_execution(%r) gave %s or changed state" % (kind, code))
        self.codes.add(code)
        self.bump("execution")

    def do_tick(self, advance_id, spec):
        self.stub.tick(self.r.choice(self.stub.ids()))
        self.bump("tick")

    def do_replay(self, advance_id, spec):
        if not self.history:
            return
        key = self.r.choice(sorted(self.history))
        op, adv, kwargs, stored = self.history[key]
        before = self.state()
        if type(stored) is str:
            code = code_of(lambda: getattr(self.m, op)(adv, idempotency_key=key, **kwargs))
            if code != stored:
                raise AssertionError("replayed rejected key gave %s, first was %s" % (code, stored))
            self.bump("replay:err")
        else:
            result = getattr(self.m, op)(adv, idempotency_key=key, **kwargs)
            want = json.loads(canon(stored))
            want["duplicate"], want["applied"] = True, None
            if json.loads(canon(result)) != want:
                raise AssertionError("replayed accepted key did not return the first result")
            self.bump("replay:ok")
        if self.state() != before:
            raise AssertionError("a replay changed state or read the source")

    def do_conflict(self, advance_id, spec):
        if not self.history:
            return
        key = self.r.choice(sorted(self.history))
        op, adv, kwargs, _stored = self.history[key]
        before = self.state()
        mode = self.r.choice(("adv", "op"))
        if mode == "adv":
            other = next(s["id"] for s in self.specs if s["id"] != adv)
            call = lambda: getattr(self.m, op)(other, idempotency_key=key, **kwargs)
        else:
            call = lambda: self.m.reconcile(adv, idempotency_key=key) if op != "reconcile" else self.m.approve(
                adv, idempotency_key=key)
        if code_of(call) != "IDEMPOTENCY_CONFLICT" or self.state() != before:
            raise AssertionError("a changed body under a used key was not rejected inertly")
        self.codes.add("IDEMPOTENCY_CONFLICT")
        self.bump("conflict")

    # invariants -------------------------------------------------------
    def check(self):
        for advance_id, case in sorted(self.cases.items()):
            self.check_view(self.m.view(advance_id), case)
        for claim_id, frozen in sorted(self.frozen.items()):
            view = self.m.view_claim(claim_id)
            check_claim_numbers(view, claim_id)
            if view["open_face"] != frozen["open_face"] or view["reserved_open"] != self.reserved(claim_id):
                raise AssertionError("%s: claim ceiling or reservation drifted from the model" % claim_id)
            if (view["confirmed_cash_on_face"], view["recovery_due_on_face"]) != (frozen["cash"], frozen["recovery"]):
                raise AssertionError("%s: cash or recovery_due drifted" % claim_id)
            if view["reserved_open"] > view["open_face"]:
                raise AssertionError("%s: shared ceiling exceeded" % claim_id)
        for claim_id, _faces in CLAIM_SHAPES:
            if claim_id not in self.frozen and code_of(lambda: self.m.view_claim(claim_id)) != "UNKNOWN_CLAIM":
                raise AssertionError("a claim with no accepted draw must be UNKNOWN_CLAIM")

    def check_view(self, view, case):
        label = view["advance_id"]
        nonneg_int(view, ("amount", "open_face", "reserved_open", "residual_unreserved", "drawn_exposure",
                          "repaid_exposure", "outstanding_exposure"), label)
        check_flags(view, ALWAYS_FALSE_FLAGS + MACHINE_FALSE_FIELDS, label)
        check_terms(view)
        if view["exposure_ledger"] != "MOCK_EXPOSURE" or view["lifecycle_authority"] != "IN_MEMORY_FSM":
            raise AssertionError("%s: exposure labels moved" % label)
        drawn = case.amount if case.phase in ("CLOSED", "DEFAULTED", "DRAWN") else 0
        want = (case.phase, drawn, case.repaid, case.outstanding)
        got = (view["phase"], view["drawn_exposure"], view["repaid_exposure"], view["outstanding_exposure"])
        if want != got:
            raise AssertionError("%s: %r != model %r" % (label, got, want))
        if view["outstanding_exposure"] + view["repaid_exposure"] != view["drawn_exposure"]:
            raise AssertionError("%s: outstanding + repaid != drawn" % label)
        if view["drawn_exposure"] > view["amount"]:
            raise AssertionError("%s: drawn exceeds the offered amount" % label)
        if [item["amount"] for item in view["repayments"]] != case.order:
            raise AssertionError("%s: repayment list drifted" % label)
        if [item["sequence"] for item in view["repayments"]] != list(range(1, len(case.order) + 1)):
            raise AssertionError("%s: repayment sequence has a gap" % label)
        if view["terminal"] is not (case.phase in TERMINAL):
            raise AssertionError("%s: terminal flag wrong" % label)
        note = {"DRAWN": "NOTED", "DEFAULTED": "NOTED", "CLOSED": "RELEASED"}.get(case.phase)
        if view["note_status"] != note:
            raise AssertionError("%s: note_status %r, model %r" % (label, view["note_status"], note))
        gate = "MOCK_COMMIT_OBSERVED" if case.gate_observed else ("UNBOUND" if case.sid is None else "BOUND")
        if view["settlement_gate"] != gate or view["mock_settlement_commit_observed"] is not case.gate_observed:
            raise AssertionError("%s: settlement gate drifted" % label)
        if view["settlement_id"] != case.sid:
            raise AssertionError("%s: settlement_id drifted" % label)
        frozen = self.frozen.get(case.spec["claim"])
        if case.phase in HOLDING_PHASES + ("CLOSED",) or (frozen is not None and frozen["canon"] == canon(case.face)):
            check_claim_numbers(view, label)
            if view["open_face"] != frozen["open_face"] or view["reserved_open"] != self.reserved(case.spec["claim"]):
                raise AssertionError("%s: claim numbers differ from the frozen model" % label)
            if (view["confirmed_cash_on_face"], view["recovery_due_on_face"]) != (frozen["cash"], frozen["recovery"]):
                raise AssertionError("%s: cash or recovery_due differ from the frozen face" % label)


# ---- directed gate matrix (section 7.5) ------------------------------------

GATE_EXPECTED = {
    "failed": "SETTLEMENT_NOT_COMMITTED",
    "wrong-claim": "SETTLEMENT_BINDING_CONFLICT",
    "gross-mismatch": "SETTLEMENT_AMOUNT_MISMATCH",
    "finality-flag": "SETTLEMENT_VIEW_REJECTED",
    "bank-debit-flag": "SETTLEMENT_VIEW_REJECTED",
}


def gate_fixture(kind, ticks=0, bind=True):
    """One approved advance bound to one stub settlement. Returns parts."""
    face, open_face = make_face("claim-a", (60_000, 30_000), (10_000, 0), "plain")
    stub = StubSettlementSource()
    stub.register("st-1", kind, "claim-a", 90_000)
    for _ in range(ticks):
        stub.tick("st-1")
    machine = CreditMachine(stub)
    machine.offer("adv-1", idempotency_key="o", face=face, amount=open_face, beneficiary_role="role-0")
    machine.approve("adv-1", idempotency_key="a")
    if bind:
        machine.bind_settlement("adv-1", idempotency_key="b", settlement_id="st-1")
    return machine, stub, face, open_face


def check_gate_attempt(machine, stub, expected, key="d-1"):
    digest, journal, stub_state = machine.state_digest(), machine.export_journal(), stub.snapshot()
    try:
        result = machine.draw("adv-1", idempotency_key=key, draw_id="dr-1")
        got = None
    except CreditError as error:
        result, got = None, error.code
    if stub.snapshot() != stub_state:
        raise AssertionError("draw wrote to the settlement source")
    if expected is None:
        if got is not None:
            raise AssertionError("committed gate rejected a draw: %s" % got)
        credit = result["credit"]
        if credit["settlement_gate"] != "MOCK_COMMIT_OBSERVED" or credit["economic_finality_claimed"] is not False:
            raise AssertionError("accepted draw reported the wrong gate or claimed finality")
        if credit["outstanding_exposure"] != credit["amount"]:
            raise AssertionError("accepted draw did not open the full exposure")
        return
    if got != expected:
        raise AssertionError("draw gave %r, expected %s" % (got, expected))
    if (machine.state_digest(), machine.export_journal()) != (digest, journal):
        raise AssertionError("a gate rejection changed state")
    view = machine.view("adv-1")
    if view["phase"] != "APPROVED" or view["note_status"] is not None or view["outstanding_exposure"] != 0:
        raise AssertionError("a gate rejection left an exposure or a note")
    if code_of(lambda: machine.view_claim("claim-a")) != "UNKNOWN_CLAIM":
        raise AssertionError("a gate rejection registered the claim")


def check_gate_matrix():
    """A draw is accepted only after the bound settlement reports COMMITTED."""
    for ticks, phase in enumerate(PHASE_ORDER):
        machine, stub, _face, _open = gate_fixture("ok", ticks)
        check_gate_attempt(machine, stub, None if phase == "COMMITTED" else "SETTLEMENT_NOT_COMMITTED")
    for kind, code in sorted(GATE_EXPECTED.items()):
        machine, stub, _face, _open = gate_fixture(kind)
        check_gate_attempt(machine, stub, code)
    machine, stub, _face, _open = gate_fixture("ok", 3)
    face, open_face = make_face("claim-a", (60_000, 30_000), (10_000, 0), "plain")
    other = CreditMachine(stub)
    other.offer("adv-1", idempotency_key="o", face=face, amount=open_face, beneficiary_role="role-0")
    other.approve("adv-1", idempotency_key="a")
    other.bind_settlement("adv-1", idempotency_key="b", settlement_id="st-missing")
    check_gate_attempt(other, stub, "UNKNOWN_SETTLEMENT")
    bare = CreditMachine()
    bare.offer("adv-1", idempotency_key="o", face=face, amount=open_face, beneficiary_role="role-0")
    bare.approve("adv-1", idempotency_key="a")
    bare.bind_settlement("adv-1", idempotency_key="b", settlement_id="st-1")
    check_gate_attempt(bare, stub, "SETTLEMENT_SOURCE_REQUIRED")
