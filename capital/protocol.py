"""Single import boundary for byte-pinned local Protocol reference modules."""
import sys
from pathlib import Path

VENDOR = Path(__file__).parent / 'vendor'
for name in ('credit_advance_f04', 'settlement_f01_f03'):
    sys.path.insert(0, str(VENDOR / name))

from credit_fsm import CreditError, CreditMachine
from settlement_fsm import SettlementMachine
from mock_settlement import MockSettlement, SettlementError
