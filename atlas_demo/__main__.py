"""Offline reviewer command."""

import argparse
import json
from pathlib import Path
import sys

from .core import load_corpus, run_demo


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Run Atlas on fictional data without network access"
    )
    parser.add_argument(
        "--config", type=Path, help="synthetic corpus JSON (defaults to packaged fixture)"
    )
    parser.add_argument("--output", type=Path, required=True, help="directory for report and cache")
    parser.add_argument(
        "--react-data", type=Path, help="write a synthetic React snapshot to an empty directory"
    )
    args = parser.parse_args()
    try:
        corpus = load_corpus(args.config)
        report = run_demo(corpus, args.output)
        if args.react_data is not None:
            from .react import export_react_snapshot

            export_react_snapshot(corpus, args.react_data)
    except (ValueError, OSError) as exc:
        print(f"demo: {exc}", file=sys.stderr)
        return 2
    print(json.dumps(report, indent=2, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    sys.exit(main())
