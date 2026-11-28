"""Strict JSONL interface to one synthetic, in-memory F04 credit session."""

import argparse
from contextlib import nullcontext
from pathlib import Path
import sys

from credit_fixture import (
    FixtureError,
    SettlementError,
    decode_json,
    exact_fields,
    load_fixture,
    validate_json,
)
from credit_fsm import CreditError
from credit_session import CreditSession
from mock_credit import PROVENANCE, _canonical


_IDENTITY = {"advance_id", "idempotency_key"}
# Explicit local selectors, not protocol commands or arbitrary attribute access.
# Method, required fields, optional fields, output field.
_DISPATCH = {
    "offer": (CreditSession.offer,
              _IDENTITY | {"face", "amount", "beneficiary_role"},
              {"product"}, "receipt"),
    "approve": (CreditSession.approve, _IDENTITY, set(), "receipt"),
    "reject": (CreditSession.reject, _IDENTITY | {"reason"}, set(), "receipt"),
    "cancel": (CreditSession.cancel, _IDENTITY | {"reason"}, set(), "receipt"),
    "bind_settlement": (CreditSession.bind_settlement,
                        _IDENTITY | {"settlement_id"}, set(), "receipt"),
    "draw": (CreditSession.draw, _IDENTITY | {"draw_id"}, set(), "receipt"),
    "repay": (CreditSession.repay,
              _IDENTITY | {"repay_id", "sequence", "amount"}, set(), "receipt"),
    "close": (CreditSession.close, _IDENTITY, set(), "receipt"),
    "default": (CreditSession.default, _IDENTITY | {"reason"}, set(), "receipt"),
    "reconcile": (CreditSession.reconcile, _IDENTITY, set(), "receipt"),
    "view": (CreditSession.view, {"advance_id"}, set(), "view"),
    "view_claim": (CreditSession.view_claim, {"claim_id"}, set(), "claim"),
}


def dispatch_request(session: CreditSession, request: dict) -> dict:
    """Check the whole request shape before calling any session method once."""
    validate_json(request)
    exact_fields(request, {"operation", "arguments"}, "request")
    operation = request["operation"]
    if type(operation) is not str or operation not in _DISPATCH:
        raise FixtureError("unsupported session operation")
    method, required, optional, result_key = _DISPATCH[operation]
    arguments = request["arguments"]
    exact_fields(arguments, required, f"{operation} arguments", optional)
    if "face" in arguments and type(arguments["face"]) is not dict:
        raise FixtureError("face must be an object")
    return {"operation": operation, "provenance": PROVENANCE,
            result_key: method(session, **arguments)}


def _error(operation, error):
    detail = ({"code": error.code} if isinstance(error, (CreditError, SettlementError))
              else {"type": type(error).__name__, "message": str(error)})
    return {"operation": operation, "provenance": PROVENANCE, "error": detail}


def _emit(value):
    print(_canonical(value), flush=True)


def run_requests(session: CreditSession, lines) -> int:
    rejected = False
    for line in lines:
        operation = None
        try:
            request = decode_json(line)
            if type(request) is dict and type(request.get("operation")) is str:
                operation = request["operation"]
            result = dispatch_request(session, request)
        except FixtureError as error:
            _emit(_error(operation, error))
            return 2
        except CreditError as error:
            # A subsequent supplied line is the only way another call occurs.
            result = _error(operation, error)
            rejected = True
        _emit(result)
    return 1 if rejected else 0


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--fixture", type=Path, required=True)
    parser.add_argument("--requests", required=True, help="JSONL path, or - for stdin")
    args = parser.parse_args(argv)
    try:
        session = load_fixture(args.fixture)
        requests = (nullcontext(sys.stdin) if args.requests == "-"
                    else Path(args.requests).open(encoding="utf-8"))
        with requests as lines:
            return run_requests(session, lines)
    except (FixtureError, CreditError, SettlementError, OSError, UnicodeError) as error:
        _emit(_error(None, error))
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
