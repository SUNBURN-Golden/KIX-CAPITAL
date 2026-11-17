#!/usr/bin/env python3
"""Stdlib offline event stress CLI. No server or live routes."""
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from capital.event_stress import main

if __name__ == '__main__':
    raise SystemExit(main())
