"""Draft 0.2 records the owner adoption of the unfilled F04 mock boundary.

Revision `F04-MOCK-TERMS-DRAFT-0.2`. JunTae adopted option A on 2026-10-09.
The reference module stays unfilled. Policy numbers stay UNDETERMINED.
This module does not name a lender, price an APR, rank notes, perfect
collateral, or recalculate a limit.
"""

from __future__ import annotations

REVISION = "F04-MOCK-TERMS-DRAFT-0.2"
CONTRACT_VERSION = "0.2"
MOCK_BOUNDARY = "UNFILLED"
ADOPTED_OPTION = "A"
ADOPTION_DECIDER = "JunTae"
ADOPTION_DATE = "2026-10-09"
POLICY_NUMBER_STATUS = "UNDETERMINED"

OWNER_ASTRA = "Astra"
OWNER_LEGAL_PARTIES = "사용자. 법률 검토의 주체와 시점은 로드맵 D-E. 당사자·관할·자료는 I10"
OWNER_PERFECTION = "사용자. 법률 검토의 주체와 시점은 로드맵 D-E. 대항요건은 I10과 같은 법무 경로"

FORBIDDEN_COMMANDS = frozenset(
    {
        "accrue",
        "debit",
        "disburse",
        "fee",
        "foreclose",
        "interest",
        "perfect",
        "priority",
        "underwrite",
    }
)

_OPTION_KEYS = frozenset({"A", "B", "C", "D"})


def _undetermined(topic: str, owner: str) -> dict:
    if not topic.strip() or not owner.strip():
        raise RuntimeError("MOCK_INVARIANT")
    return {"topic": topic, "status": "UNDETERMINED", "owner": owner}


def _item(
    item_id: str,
    *,
    mock_effect: str,
    options: dict,
    current_refusal: tuple,
    non_claim_flags: tuple,
    undetermined: tuple,
    covered_by: tuple,
    observed_fixture: dict | None = None,
) -> dict:
    if set(options) - _OPTION_KEYS or "A" not in options:
        raise RuntimeError("MOCK_INVARIANT")
    if ADOPTED_OPTION not in options:
        raise RuntimeError("MOCK_INVARIANT")
    return {
        "id": item_id,
        "mock_boundary": MOCK_BOUNDARY,
        "adopted_option": ADOPTED_OPTION,
        "adoption_decider": ADOPTION_DECIDER,
        "adoption_date": ADOPTION_DATE,
        "decided_value": None,
        "policy_number_status": POLICY_NUMBER_STATUS,
        "mock_effect": mock_effect,
        "recommendation": ADOPTED_OPTION,
        "options": options,
        "current_refusal": current_refusal,
        "non_claim_flags": non_claim_flags,
        "observed_fixture": observed_fixture,
        "undetermined": undetermined,
        "covered_by": covered_by,
    }


ITEMS = (
    _item(
        "legal-parties",
        mock_effect="ROLE_LABEL_ONLY",
        options={
            "A": "Store the role label only. Do not bind a lender, borrower, secured party, or refund debtor.",
            "B": "Record a caller-supplied identifier as the legal party.",
            "C": "Name a fixed legal entity in the contract.",
        },
        current_refusal=(),
        non_claim_flags=("legal_debtor_bound",),
        undetermined=(
            _undetermined(
                "legal identity of the lender, borrower, secured party, and refund debtor",
                OWNER_LEGAL_PARTIES,
            ),
        ),
        covered_by=(
            "test_mock_credit.CreditAdvanceMockTests.test_adopted_boundary_stays_unfilled_on_the_mock",
        ),
    ),
    _item(
        "interest-apr-schedule",
        mock_effect="INTEREST_UNDEFINED",
        options={
            "A": "Do not define interest, fees, APR, tenor, or a repayment schedule.",
            "B": "Adopt a synthetic fixed APR and schedule as the mock product.",
            "C": "Record a caller-supplied APR and do not accrue interest.",
        },
        current_refusal=("CREDIT_PRODUCT_UNDEFINED",),
        non_claim_flags=("interest_defined",),
        undetermined=(
            _undetermined(
                "APR, fee, tenor, and repayment schedule",
                OWNER_ASTRA,
            ),
        ),
        covered_by=(
            "test_mock_credit.CreditAdvanceMockTests.test_adopted_boundary_stays_unfilled_on_the_mock",
            "test_credit_fsm.CreditFsmTests.test_adopted_boundary_does_not_price_rank_or_recalculate",
        ),
    ),
    _item(
        "seniority",
        mock_effect="UNORDERED_RESERVATION",
        options={
            "A": "Do not rank notes. The sum of reservations stays inside the open face.",
            "B": "Treat acceptance order as seniority.",
            "C": "Use beneficiary_role as the rank key.",
            "D": "Accept a caller-supplied rank.",
        },
        current_refusal=("CREDIT_PRODUCT_UNDEFINED", "ADVANCE_EXCEEDS_OPEN_FACE"),
        non_claim_flags=("priority_bound",),
        undetermined=(
            _undetermined(
                "seniority and distribution rank among notes",
                OWNER_ASTRA,
            ),
        ),
        covered_by=(
            "test_credit_fsm.CreditFsmTests.test_adopted_boundary_does_not_price_rank_or_recalculate",
        ),
    ),
    _item(
        "perfection",
        mock_effect="NOT_PERFECTED",
        options={
            "A": "Do not claim perfection, registration, possession, or an external pledge.",
            "B": "Set a perfection flag to true.",
            "C": "Record registration or possession identifiers as perfection.",
        },
        current_refusal=("CREDIT_PRODUCT_UNDEFINED",),
        non_claim_flags=("collateral_perfected", "external_pledge_complete"),
        undetermined=(
            _undetermined(
                "perfection, registration, possession, and external pledge",
                OWNER_PERFECTION,
            ),
        ),
        covered_by=(
            "test_mock_credit.CreditAdvanceMockTests.test_adopted_boundary_stays_unfilled_on_the_mock",
        ),
    ),
    _item(
        "limit-recalculation",
        mock_effect="SNAPSHOT_FROZEN",
        options={
            "A": "Freeze the ceiling at the first accepted face. Do not add confirmed cash or recovery due.",
            "B": "Recompute the ceiling from unpaid face on every query.",
            "C": "Include confirmed cash or recovery due in the limit.",
            "D": "Lower the limit only after distribution or refund.",
        },
        current_refusal=("FACE_SNAPSHOT_FROZEN",),
        non_claim_flags=(),
        observed_fixture={
            "snapshot_frozen": True,
            "confirmed_cash_counts_toward_ceiling": False,
            "recovery_due_counts_toward_ceiling": False,
        },
        undetermined=(
            _undetermined(
                "limit recalculation formula after the face snapshot",
                OWNER_ASTRA,
            ),
        ),
        covered_by=(
            "test_mock_credit.CreditAdvanceMockTests.test_adopted_boundary_stays_unfilled_on_the_mock",
            "test_credit_fsm.CreditFsmTests.test_adopted_boundary_does_not_price_rank_or_recalculate",
        ),
    ),
)


def item(item_id: str) -> dict:
    for row in ITEMS:
        if row["id"] == item_id:
            return row
    raise KeyError(item_id)


def forbidden_commands() -> frozenset:
    return FORBIDDEN_COMMANDS


def boundary() -> dict:
    """Compact view record. It carries no APR, rank, party, or formula."""

    return {
        "revision": REVISION,
        "contract_version": CONTRACT_VERSION,
        "mock_boundary": MOCK_BOUNDARY,
        "adopted_option": ADOPTED_OPTION,
        "adoption_decider": ADOPTION_DECIDER,
        "adoption_date": ADOPTION_DATE,
        "policy_number_status": POLICY_NUMBER_STATUS,
        "decided_value": None,
        "terms": {
            row["id"]: {
                "adopted_option": ADOPTED_OPTION,
                "mock_effect": row["mock_effect"],
                "policy_number_status": POLICY_NUMBER_STATUS,
                "decided_value": None,
            }
            for row in ITEMS
        },
    }
