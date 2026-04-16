#!/usr/bin/env python3
import argparse
import csv
import json
import math


def percentile(sorted_values, pct):
    if not sorted_values:
        return 0.0
    if len(sorted_values) == 1:
        return float(sorted_values[0])
    rank = (len(sorted_values) - 1) * (pct / 100.0)
    lower = math.floor(rank)
    upper = math.ceil(rank)
    if lower == upper:
        return float(sorted_values[int(rank)])
    weight = rank - lower
    return float(sorted_values[lower] * (1 - weight) + sorted_values[upper] * weight)


def main():
    parser = argparse.ArgumentParser(description="Summarize JMeter JTL output.")
    parser.add_argument("--jtl", required=True)
    args = parser.parse_args()

    elapsed_values = []
    failures = 0
    timestamps = []
    with open(args.jtl, newline="", encoding="utf-8") as file:
        reader = csv.DictReader(file)
        for row in reader:
            elapsed_values.append(int(row["elapsed"]))
            timestamps.append(int(row["timeStamp"]))
            if row["success"].lower() != "true":
                failures += 1

    total_requests = len(elapsed_values)
    if total_requests == 0:
        raise RuntimeError("JTL file has no samples")

    elapsed_values.sort()
    start = min(timestamps)
    end = max(timestamps)
    duration_seconds = max((end - start) / 1000.0, 0.001)
    summary = {
        "requests": total_requests,
        "duration_seconds": round(duration_seconds, 3),
        "qps": round(total_requests / duration_seconds, 2),
        "p50_ms": round(percentile(elapsed_values, 50), 2),
        "p95_ms": round(percentile(elapsed_values, 95), 2),
        "p99_ms": round(percentile(elapsed_values, 99), 2),
        "error_rate_pct": round((failures / total_requests) * 100, 4),
    }
    print(json.dumps(summary, ensure_ascii=False))


if __name__ == "__main__":
    main()
