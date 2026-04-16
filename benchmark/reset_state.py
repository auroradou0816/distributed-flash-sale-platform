#!/usr/bin/env python3
import argparse
import json
import os
import subprocess
from datetime import datetime, timedelta

import pymysql
import redis


def get_mysql_connection(args):
    return pymysql.connect(
        host=args.mysql_host,
        port=args.mysql_port,
        user=args.mysql_user,
        password=args.mysql_password,
        database=args.mysql_db,
        charset="utf8mb4",
        autocommit=True,
    )


def get_redis_client(args):
    return redis.Redis(
        host=args.redis_host,
        port=args.redis_port,
        password=args.redis_password or None,
        decode_responses=True,
    )


def reset_mysql(args):
    begin_time = (datetime.now() - timedelta(days=1)).strftime("%Y-%m-%d %H:%M:%S")
    end_time = (datetime.now() + timedelta(days=1)).strftime("%Y-%m-%d %H:%M:%S")
    with get_mysql_connection(args) as conn:
        with conn.cursor() as cursor:
            cursor.execute(
                """
                INSERT INTO tb_voucher
                    (id, shop_id, title, sub_title, rules, pay_value, actual_value, type, status, create_time, update_time)
                VALUES
                    (%s, 1, 'Phase0基线秒杀券', '1000并发压测', '仅用于Phase 0基线压测', 100, 100, 1, 1, NOW(), NOW())
                ON DUPLICATE KEY UPDATE
                    shop_id = VALUES(shop_id),
                    title = VALUES(title),
                    sub_title = VALUES(sub_title),
                    rules = VALUES(rules),
                    pay_value = VALUES(pay_value),
                    actual_value = VALUES(actual_value),
                    type = VALUES(type),
                    status = VALUES(status),
                    update_time = NOW()
                """,
                (args.voucher_id,),
            )
            cursor.execute(
                """
                INSERT INTO tb_seckill_voucher
                    (voucher_id, stock, create_time, begin_time, end_time, update_time)
                VALUES
                    (%s, %s, NOW(), %s, %s, NOW())
                ON DUPLICATE KEY UPDATE
                    stock = VALUES(stock),
                    begin_time = VALUES(begin_time),
                    end_time = VALUES(end_time),
                    update_time = NOW()
                """,
                (args.voucher_id, args.stock, begin_time, end_time),
            )
            cursor.execute("DELETE FROM tb_voucher_order WHERE voucher_id = %s", (args.voucher_id,))


def reset_redis(args):
    client = get_redis_client(args)
    stock_key = f"seckill:stock:{args.voucher_id}"
    order_key = f"seckill:order:{args.voucher_id}"
    stream_key = "stream.orders"
    client.delete(stock_key)
    client.set(stock_key, args.stock)
    client.delete(order_key)
    client.delete(stream_key)
    try:
        client.xgroup_create(stream_key, "g1", id="0", mkstream=True)
    except redis.ResponseError as exc:
        if "BUSYGROUP" not in str(exc):
            raise


def reset_mq_offsets(args):
    if not args.mq_reset_offsets:
        return {"enabled": False, "reset": False}

    command = [
        args.mqadmin_bin,
        "resetOffsetByTime",
        "-n",
        args.mq_name_server,
        "-g",
        args.mq_consumer_group,
        "-t",
        args.mq_topic,
        "-s",
        args.mq_reset_timestamp,
    ]
    if args.mq_force_reset:
        command.extend(["-f", "true"])

    completed = subprocess.run(
        command,
        check=True,
        capture_output=True,
        text=True,
    )
    return {
        "enabled": True,
        "reset": True,
        "command": command,
        "stdout": completed.stdout.strip(),
    }


def main():
    parser = argparse.ArgumentParser(description="Reset Phase 0 benchmark data.")
    parser.add_argument("--voucher-id", type=int, default=int(os.getenv("VOUCHER_ID", "10")))
    parser.add_argument("--stock", type=int, default=int(os.getenv("BENCHMARK_STOCK", "100")))
    parser.add_argument("--mysql-host", default=os.getenv("MYSQL_HOST", "127.0.0.1"))
    parser.add_argument("--mysql-port", type=int, default=int(os.getenv("MYSQL_PORT", "3306")))
    parser.add_argument("--mysql-user", default=os.getenv("MYSQL_USER", "root"))
    parser.add_argument("--mysql-password", default=os.getenv("MYSQL_PASSWORD", ""))
    parser.add_argument("--mysql-db", default=os.getenv("MYSQL_DB", "hmdp"))
    parser.add_argument("--redis-host", default=os.getenv("REDIS_HOST", "127.0.0.1"))
    parser.add_argument("--redis-port", type=int, default=int(os.getenv("REDIS_PORT", "6380")))
    parser.add_argument("--redis-password", default=os.getenv("REDIS_PASSWORD", ""))
    parser.add_argument("--mq-reset-offsets", action="store_true")
    parser.add_argument("--mqadmin-bin", default=os.getenv("MQADMIN_BIN", "mqadmin"))
    parser.add_argument("--mq-name-server", default=os.getenv("MQ_NAME_SERVER", "localhost:9876"))
    parser.add_argument("--mq-consumer-group", default=os.getenv("MQ_CONSUMER_GROUP", "seckill-order-consumer-group"))
    parser.add_argument("--mq-topic", default=os.getenv("MQ_TOPIC", "seckill-order-topic"))
    parser.add_argument("--mq-reset-timestamp", default=os.getenv("MQ_RESET_TIMESTAMP", "now"))
    parser.add_argument("--mq-force-reset", action="store_true")
    args = parser.parse_args()

    reset_mysql(args)
    reset_redis(args)
    mq_result = reset_mq_offsets(args)
    print(
        json.dumps(
            {
                "voucher_id": args.voucher_id,
                "stock": args.stock,
                "mysql": f"{args.mysql_host}:{args.mysql_port}/{args.mysql_db}",
                "redis": f"{args.redis_host}:{args.redis_port}",
                "mq": mq_result,
            },
            ensure_ascii=False,
        )
    )


if __name__ == "__main__":
    main()
