#!/usr/bin/env python3
import argparse
import json
import os
import time

import pymysql
import redis


def fetch_state(args):
    with pymysql.connect(
        host=args.mysql_host,
        port=args.mysql_port,
        user=args.mysql_user,
        password=args.mysql_password,
        database=args.mysql_db,
        charset="utf8mb4",
        autocommit=True,
    ) as conn:
        with conn.cursor() as cursor:
            cursor.execute("SELECT COUNT(*), COUNT(DISTINCT user_id) FROM tb_voucher_order WHERE voucher_id = %s", (args.voucher_id,))
            order_count, distinct_users = cursor.fetchone()
            cursor.execute("SELECT stock FROM tb_seckill_voucher WHERE voucher_id = %s", (args.voucher_id,))
            row = cursor.fetchone()
            db_stock = row[0] if row else None

    redis_client = redis.Redis(
        host=args.redis_host,
        port=args.redis_port,
        password=args.redis_password or None,
        decode_responses=True,
    )
    redis_stock = redis_client.get(f"seckill:stock:{args.voucher_id}")
    redis_order_count = redis_client.scard(f"seckill:order:{args.voucher_id}")
    pending = redis_client.xpending("stream.orders", "g1")["pending"] if redis_client.exists("stream.orders") else 0

    return {
        "order_count": int(order_count),
        "distinct_users": int(distinct_users),
        "db_stock": None if db_stock is None else int(db_stock),
        "redis_stock": None if redis_stock is None else int(redis_stock),
        "redis_order_count": int(redis_order_count),
        "pending_messages": int(pending),
    }


def main():
    parser = argparse.ArgumentParser(description="Check baseline order consistency.")
    parser.add_argument("--voucher-id", type=int, default=int(os.getenv("VOUCHER_ID", "10")))
    parser.add_argument("--initial-stock", type=int, default=int(os.getenv("BENCHMARK_STOCK", "100")))
    parser.add_argument("--expected-orders", type=int, default=int(os.getenv("BENCHMARK_EXPECTED_ORDERS", "100")))
    parser.add_argument("--timeout-seconds", type=int, default=int(os.getenv("CONSISTENCY_TIMEOUT_SECONDS", "20")))
    parser.add_argument("--poll-interval", type=float, default=float(os.getenv("CONSISTENCY_POLL_INTERVAL", "0.5")))
    parser.add_argument("--mysql-host", default=os.getenv("MYSQL_HOST", "127.0.0.1"))
    parser.add_argument("--mysql-port", type=int, default=int(os.getenv("MYSQL_PORT", "3306")))
    parser.add_argument("--mysql-user", default=os.getenv("MYSQL_USER", "root"))
    parser.add_argument("--mysql-password", default=os.getenv("MYSQL_PASSWORD", ""))
    parser.add_argument("--mysql-db", default=os.getenv("MYSQL_DB", "flash_sale"))
    parser.add_argument("--redis-host", default=os.getenv("REDIS_HOST", "127.0.0.1"))
    parser.add_argument("--redis-port", type=int, default=int(os.getenv("REDIS_PORT", "6380")))
    parser.add_argument("--redis-password", default=os.getenv("REDIS_PASSWORD", ""))
    args = parser.parse_args()

    deadline = time.time() + args.timeout_seconds
    state = None
    while time.time() <= deadline:
        state = fetch_state(args)
        if state["order_count"] == args.expected_orders and state["db_stock"] == args.initial_stock - args.expected_orders:
            break
        time.sleep(args.poll_interval)

    state["expected_orders"] = args.expected_orders
    state["initial_stock"] = args.initial_stock
    state["pending_cleared"] = state["pending_messages"] == 0
    state["consistent"] = (
        state["order_count"] == args.expected_orders
        and state["distinct_users"] == args.expected_orders
        and state["db_stock"] == args.initial_stock - args.expected_orders
        and state["redis_stock"] == args.initial_stock - args.expected_orders
        and state["redis_order_count"] == args.expected_orders
    )
    print(json.dumps(state, ensure_ascii=False))


if __name__ == "__main__":
    main()
