"""Single import boundary for byte-pinned local Protocol reference modules."""
import hashlib
import json

from capital.resources import VENDOR, install_vendor_path

install_vendor_path()

from credit_fsm import CreditError, CreditMachine
from settlement_fsm import SettlementMachine
from mock_settlement import MockSettlement, SettlementError
from settlement_variance import VarianceObservationError, observe_settlement_variance
from shared_exposure import SharedExposureError, observe_shared_exposure


def matches_workspace_state_digest(book, expected):
    """Verify the current digest or the exact pre-open_terms F04 case shape."""
    if book.state_digest() == expected:
        return True
    state = json.loads(book.canonical_state())
    for case in state['cases']:
        case.pop('open_terms', None)
    raw = json.dumps(state, sort_keys=True, separators=(',', ':'),
                     ensure_ascii=False, allow_nan=False).encode('utf-8')
    return hashlib.sha256(raw).hexdigest() == expected
