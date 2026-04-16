#!/usr/bin/env python3
import argparse
import json
from pathlib import Path


NUMERIC_KEYS = [
    "qps",
    "p50_ms",
    "p95_ms",
    "p99_ms",
    "error_rate_pct",
    "duration_seconds",
]


def main():
    parser = argparse.ArgumentParser(description="Average benchmark summary JSON files.")
    parser.add_argument("files", nargs="+")
    args = parser.parse_args()

    summaries = [json.loads(Path(path).read_text(encoding="utf-8")) for path in args.files]
    result = {"rounds": len(summaries)}
    for key in NUMERIC_KEYS:
        result[key] = round(sum(item[key] for item in summaries) / len(summaries), 2)
    print(json.dumps(result, ensure_ascii=False))


if __name__ == "__main__":
    main()
