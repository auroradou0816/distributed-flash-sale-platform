# Phase 6 — AWS Production Benchmark

End-to-end benchmark against the full cloud stack on `us-east-1`, 2026-04-16.

## Setup

| Component | Location | Instance / Size |
|---|---|---|
| JMeter client | Laptop (San Diego) | — |
| App (Spring Boot + RocketMQ producer/consumer) | EC2 in public subnet, us-east-1a | t3.small, Docker container `flash-sale-platform:latest` (154 MB, linux/amd64) |
| RocketMQ namesrv + broker | EC2 in public subnet, us-east-1a | t3.small, `apache/rocketmq:5.1.4` |
| MySQL | RDS, private subnet | db.t3.micro, MySQL 8.0 |
| Redis | ElastiCache, private subnet | cache.t3.micro, Redis 7.x |
| Data plane access from laptop | via SSH tunnel through app-host | 127.0.0.1:6389 → ElastiCache:6379; 127.0.0.1:3310 → RDS:3306 |

Test plan reused **unchanged** from Phase 0 (`benchmark/seckill-baseline.jmx`): 1000 concurrent threads, 1 s ramp-up, `stock=100`, voucher id `10`, 3 rounds with consistency check between rounds.

## Per-round results

| Round | Requests | Duration (s) | QPS | P50 (ms) | P95 (ms) | P99 (ms) | Errors | Orders | Stock drained | Pending |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| 1 | 1000 | 0.531 | 1883 | 1192.5 | 1962.1 | 2040.0 | 0 | 100 | 0 | 0 |
| 2 | 1000 | 0.823 | 1215 | 857.5 | 993.1 | 1075.2 | 0 | 100 | 0 | 0 |
| 3 | 1000 | 0.774 | 1292 | 908.0 | 993.1 | 1047.1 | 0 | 100 | 0 | 0 |
| **avg** | — | — | **1463.4** | **986.0** | **1316.1** | **1387.4** | **0.00%** | 100 × 3 | ✓ | 0 |

All three rounds: `consistent: true`, `distinct_users == order_count == initial_stock == 100`, `pending_messages == 0`.

## Honest readout

- **Throughput**: AWS avg QPS `1463` is slightly **higher** than the local baseline's `1190`. This is not "AWS makes the app faster" — it reflects the removal of laptop-side resource contention. The local runs had JMeter, Spring Boot, MySQL, Redis, and RocketMQ all sharing one laptop; on AWS, each component has its own instance, and only JMeter runs on the laptop.
- **Latency**: client-side P99 `1387 ms` is ~6× the local `181 ms`. The laptop↔us-east-1 base RTT adds ~200 ms/request, plus TLS-less TCP setup cost for 1000 fresh connections inside a 1 s ramp-up window. Server-side P99 is not measured here; to isolate it, run JMeter from a same-AZ EC2. Deferred.
- **Correctness invariant — the important bit**: every round produced exactly 100 orders for 100 units of stock across 100 distinct users, with 0 pending messages. This holds even though the test fires 1000 concurrent requests against 100 stock, and the RocketMQ consumer replays on at-least-once semantics. The DB unique index `uk_user_voucher` + `DuplicateKeyException` fast-ack added in Phase 2 is what makes this safe.

## Reproduction

```bash
# 1) SSH tunnel to private data plane
ssh -f -N \
  -L 6389:<REDIS_ENDPOINT>:6379 \
  -L 3310:<DB_ENDPOINT>:3306 \
  -i ~/.ssh/flash-sale-keypair.pem ec2-user@<APP_PUBLIC_IP>

# 2) env for run_baseline.sh
export BENCHMARK_HOST=<APP_PUBLIC_IP> BENCHMARK_PORT=8081
export APP_BASE_URL="http://<APP_PUBLIC_IP>:8081"
export REDIS_HOST=127.0.0.1 REDIS_PORT=6389
export MYSQL_HOST=127.0.0.1 MYSQL_PORT=3310
export MYSQL_USER=appadmin MYSQL_PASSWORD="<pw>" MYSQL_DB=flash_sale
export VOUCHER_ID=10 BENCHMARK_STOCK=100 EXPECTED_ORDERS=100
export THREADS=1000 RAMP_UP_SECONDS=1
export PYTHON_BIN="$PWD/benchmark/.venv/bin/python"

# 3) Run (reuses unchanged seckill-baseline.jmx)
bash benchmark/run_baseline.sh

# 4) Results under benchmark/results/phase6-aws/
```

Deployment of the underlying AWS stack: see [docs/aws-deploy.md](../docs/aws-deploy.md).
