import argparse
import hashlib
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / 'tests'))

from capital.observation import LocalFakeObservation
from test_observation_port import CORPUS, CORPUS_SHA256, run_observation_vectors


def main():
    parser = argparse.ArgumentParser(description='Read-only SIMULATED observation vector check')
    parser.add_argument('--check', required=True, action='store_true')
    parser.add_argument('--file', type=Path, default=CORPUS)
    args = parser.parse_args()
    try:
        if hashlib.sha256(args.file.read_bytes()).hexdigest() != CORPUS_SHA256:
            raise ValueError('provider corpus byte drift')
        run_observation_vectors(LocalFakeObservation, args.file)
    except (OSError, ValueError, AssertionError, KeyError, TypeError) as exc:
        print(f'SIMULATED observation vectors FAIL: {exc}', file=sys.stderr)
        return 1
    print('SIMULATED observation vectors PASS; NOT_BOUND; applied=false; funds_executed=false')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
