#!/usr/bin/env python3
"""Read one explicit local file and emit SIMULATED observation diagnostics."""
import argparse
import os
import stat
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from capital.observation import safe
from capital.observation_triage import MAX_BYTES, ContractError, InputError, parse_input, serialize, triage


def error(code, message):
    sys.stderr.buffer.write(serialize(safe(error_code=code, message=message)))


class Parser(argparse.ArgumentParser):
    def error(self, message):
        error('ARGUMENT_ERROR', message)
        self.exit(2)


def read_input(path):
    # Nonblocking open ensures FIFOs cannot hang the offline reader. fstat
    # checks the opened descriptor rather than racing a path-only check.
    fd = os.open(path, os.O_RDONLY | os.O_NONBLOCK)
    with os.fdopen(fd, 'rb') as stream:
        if not stat.S_ISREG(os.fstat(stream.fileno()).st_mode):
            raise InputError('input must be a local regular file')
        return parse_input(stream.read(MAX_BYTES + 1))


def main(argv=None):
    parser = Parser(description=__doc__)
    parser.add_argument('--input', required=True, type=Path)
    args = parser.parse_args(argv)
    try:
        document = read_input(args.input)
        report = triage(document['facts'], bindings=document['bindings'])
        output = serialize(report)
    except (InputError, OSError) as exc:
        error('INVALID_INPUT', 'Cannot read a bounded synthetic input file.' if isinstance(exc, OSError) else str(exc))
        return 1
    except ContractError as exc:
        error(exc.code, str(exc))
        return 3
    except Exception:
        error('INTERNAL_ERROR', 'Observation diagnostics failed.')
        return 3
    sys.stdout.buffer.write(output)
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
