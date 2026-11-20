"""Run a caller-selected synthetic credit transcript and response-derived reads."""

import argparse
from pathlib import Path

from credit_client import CreditClient, CreditTransportUncertainty
from credit_fixture import FixtureError, decode_json
from mock_credit import _canonical


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--fixture', type=Path, required=True)
    parser.add_argument('--requests', type=Path, required=True, help='caller-selected JSONL file')
    parser.add_argument('--cleanup-timeout', type=float, required=True)
    args = parser.parse_args(argv)
    try:
        client = CreditClient.launch(args.fixture, cleanup_timeout=args.cleanup_timeout)
    except ValueError as error:
        parser.error(str(error))
    try:
        def send(request):
            reply = client.request(request)
            print(_canonical(reply), flush=True)
            return reply

        try:
            with args.requests.open(encoding='utf-8') as lines:
                for line in lines:
                    reply = send(decode_json(line))
                    if 'error' in reply:
                        return 1
                    if 'receipt' in reply:
                        credit = reply['receipt']['credit']
                        reads = [('view', {'advance_id': credit['advance_id']})]
                        # A claim exists only after the first accepted draw/note.
                        if credit['snapshot_frozen']:
                            reads.append(('view_claim', {'claim_id': credit['claim_id']}))
                        for operation, arguments in reads:
                            if 'error' in send(dict(operation=operation, arguments=arguments)):
                                return 1
        finally:
            exit_code = client.close()
    except (CreditTransportUncertainty, FixtureError, OSError, UnicodeError, TypeError) as error:
        parser.exit(2, f'{error}\n')
    return 0 if exit_code == 0 else 1


if __name__ == '__main__':
    raise SystemExit(main())
