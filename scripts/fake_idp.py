#!/usr/bin/env python3
"""Mint LOCAL_FAKE_IDP session tokens for the four synthetic roles.

HS256 with the committed test-vector key. Not a credential, not an identity
provider, no network or file access. Identity and authentication stay NOT_BOUND.
"""
import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from capital import idp_fake  # noqa: E402
from capital.auth import ROLES  # noqa: E402


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument('--role', choices=ROLES, help='print one token')
    group.add_argument('--all', action='store_true', help='print a JSON map of role to token')
    parser.add_argument('--ttl', type=int, default=idp_fake.DEFAULT_TTL_S, help='lifetime in seconds')
    parser.add_argument('--now', type=int, default=None, help='fixed issue time (epoch seconds)')
    args = parser.parse_args(argv)
    try:
        if args.all:
            print(json.dumps({role: idp_fake.mint(role, now=args.now, ttl=args.ttl) for role in ROLES}, indent=2))
        else:
            print(idp_fake.mint(args.role, now=args.now, ttl=args.ttl))
    except ValueError as exc:
        parser.error(str(exc))
    print(f'{idp_fake.LABEL} token, test-vector key, not a credential, NOT_BOUND identity', file=sys.stderr)
    return 0


if __name__ == '__main__':
    sys.exit(main())
