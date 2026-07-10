"""Capture a py-spy flamegraph of the headless benchmark.

Usage:
    python tools/profile_pyspy.py --seconds 120 --speed 5 -o flamegraph.svg
Extra args after `--` are forwarded to tools/benchmark_ai_spectator.py.
Requires `pip install py-spy`.
"""
from __future__ import annotations

import argparse
import os
import shutil
import subprocess
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def main():
    parser = argparse.ArgumentParser(description="py-spy flamegraph of the headless benchmark.")
    parser.add_argument("--seconds", type=float, default=120)
    parser.add_argument("--speed", type=float, default=5.0)
    parser.add_argument("-o", "--output", default="flamegraph.svg")
    parser.add_argument("--rate", type=int, default=200, help="Sampling rate (Hz).")
    parser.add_argument("rest", nargs="*", help="Extra benchmark args (after --).")
    args = parser.parse_args()

    py_spy = shutil.which("py-spy")
    if py_spy is None:
        print("py-spy not found; install with `pip install py-spy`.", file=sys.stderr)
        return 1

    cmd = [
        py_spy,
        "record",
        "--rate",
        str(args.rate),
        "-o",
        args.output,
        "--",
        sys.executable,
        os.path.join(ROOT, "tools", "benchmark_ai_spectator.py"),
        "--seconds",
        str(args.seconds),
        "--speed",
        str(args.speed),
        *args.rest,
    ]
    print(" ".join(cmd))
    return subprocess.call(cmd, cwd=ROOT)


if __name__ == "__main__":
    raise SystemExit(main())
