#!/usr/bin/env python3
import argparse
import json
import os
import pathlib
import urllib.error
import urllib.request
from concurrent.futures import ThreadPoolExecutor, as_completed

import redis


def login(base_url, phone, code):
    payload = json.dumps({"phone": phone, "code": code}).encode("utf-8")
    request = urllib.request.Request(
        f"{base_url.rstrip('/')}/user/login",
        data=payload,
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    with urllib.request.urlopen(request, timeout=5) as response:
        body = json.loads(response.read().decode("utf-8"))
    if not body.get("success"):
        raise RuntimeError(f"login failed for {phone}: {body}")
    token = body.get("data")
    if not token:
        raise RuntimeError(f"missing token for {phone}: {body}")
    return token


def prepare_single(index, args, redis_client):
    phone = f"{args.phone_prefix}{index:08d}"
    redis_client.set(f"login:code:{phone}", args.code, ex=120)
    token = login(args.base_url, phone, args.code)
    return index, token


def main():
    parser = argparse.ArgumentParser(description="Generate login tokens for benchmark users.")
    parser.add_argument("--count", type=int, default=int(os.getenv("BENCHMARK_USER_COUNT", "1000")))
    parser.add_argument("--base-url", default=os.getenv("APP_BASE_URL", "http://127.0.0.1:8081"))
    parser.add_argument("--redis-host", default=os.getenv("REDIS_HOST", "127.0.0.1"))
    parser.add_argument("--redis-port", type=int, default=int(os.getenv("REDIS_PORT", "6380")))
    parser.add_argument("--redis-password", default=os.getenv("REDIS_PASSWORD", ""))
    parser.add_argument("--code", default=os.getenv("BENCHMARK_LOGIN_CODE", "123456"))
    parser.add_argument("--phone-prefix", default=os.getenv("BENCHMARK_PHONE_PREFIX", "138"))
    parser.add_argument("--output", default=os.getenv("TOKEN_FILE", "benchmark/data/tokens.txt"))
    parser.add_argument("--workers", type=int, default=int(os.getenv("TOKEN_WORKERS", "50")))
    args = parser.parse_args()

    redis_client = redis.Redis(
        host=args.redis_host,
        port=args.redis_port,
        password=args.redis_password or None,
        decode_responses=True,
    )

    pathlib.Path(args.output).parent.mkdir(parents=True, exist_ok=True)
    tokens = {}
    with ThreadPoolExecutor(max_workers=args.workers) as executor:
        futures = [executor.submit(prepare_single, i, args, redis_client) for i in range(args.count)]
        for future in as_completed(futures):
            try:
                index, token = future.result()
                tokens[index] = token
            except urllib.error.HTTPError as exc:
                raise RuntimeError(f"HTTP error while preparing tokens: {exc}") from exc

    if len(tokens) != args.count:
        raise RuntimeError(f"expected {args.count} tokens, got {len(tokens)}")

    with open(args.output, "w", encoding="utf-8") as file:
        for index in range(args.count):
            file.write(tokens[index] + "\n")

    print(json.dumps({"count": args.count, "output": args.output}, ensure_ascii=False))


if __name__ == "__main__":
    main()
