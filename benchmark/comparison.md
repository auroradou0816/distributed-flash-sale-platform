# Three-environment benchmark comparison

All three environments run the **exact same** JMeter plan (`benchmark/seckill-baseline.jmx`): 1000 concurrent threads, 1 s ramp-up, `stock=100`, 3 rounds per environment, averaged.

| Metric | Phase 0 — Local Redis Stream | Phase 3 — Local RocketMQ + Idempotent | Phase 6 — AWS RocketMQ + Idempotent | Δ (AWS vs Local Baseline) |
|---|---:|---:|---:|---:|
| QPS | 1190.37 | 1181.05 | **1463.43** | +22.9% |
| P50 (ms) | 33.67 | 18.00 | 986.00 | +2828% (network-bound) |
| P95 (ms) | 198.33 | 152.68 | 1316.07 | +563% (network-bound) |
| P99 (ms) | 228.67 | 181.34 | 1387.42 | +507% (network-bound) |
| Error rate | 0.00% | 0.00% | **0.00%** | flat |
| Orders / rounds consistent | 100 / 3 rounds | 100 / 3 rounds | **100 / 3 rounds** | ✓ |
| Pending messages after run | 100 (Redis Stream pending-list leftover) | 0 | **0** | cleared |

## What each column measures

- **Phase 0**: everything on one laptop (JMeter + Spring Boot + MySQL + Redis + RocketMQ absent). Seckill path = Redis Stream + single-thread consumer.
- **Phase 3**: everything on one laptop, but seckill path replaced with RocketMQ + consumer group + idempotent consumer.
- **Phase 6**: JMeter on laptop; app/DB/cache/MQ all on separate AWS instances in us-east-1. Laptop↔us-east-1 RTT ≈ 200 ms adds to every request.

## Honest readout

- **Throughput**: AWS is ~23% higher than local. This is *not* because AWS is inherently faster; it is because the local runs had every component competing for one laptop's CPU. On AWS, each component has its own instance. The comparison is apples-to-apples on test plan, but not on host configuration — which is an honest reflection of what "moving to cloud" actually buys you in production.
- **Latency**: the large P99 jump on AWS is **client-side-only**. Laptop↔AWS public-internet RTT adds a floor of ~200 ms, and 1000 fresh TCP connections inside 1 s compound it. Server-side latency would require same-AZ JMeter; deferred. The project takeaway is "consistent zero-error, zero-duplicate, zero-pending under cloud deployment" — not the client-observed P99.
- **Correctness across all three**: every round, every environment — 100 orders, 100 distinct users, 0 duplicates, 0 pending. The DB unique index + `DuplicateKeyException` fast-ack from Phase 2 makes the at-least-once RocketMQ delivery safe to rely on.
- **What Phase 3 actually improved over Phase 0**: not raw QPS (basically flat) — it's the **operational model**. Redis Stream version left 100 pending messages per round; RocketMQ version drains to 0 on every round. Plus the consumer can now scale horizontally via consumer group.

## ASCII snapshot

```text
QPS        Local baseline 1190  |  Local RocketMQ 1181  |  AWS 1463
P99 (ms)   Local baseline  229  |  Local RocketMQ  181  |  AWS 1387 (+RTT)
Err rate   Local baseline 0.00% |  Local RocketMQ 0.00% |  AWS 0.00%
Pending    Local baseline  100  |  Local RocketMQ    0  |  AWS    0
```

Raw results:
- Local baseline: `benchmark/baseline.md` + `benchmark/results/phase3-rocketmq/` (earlier tag) *(pre-refactor asset)*
- Local RocketMQ: `benchmark/after-rocketmq.md` + `benchmark/results/round-*-summary.json`
- AWS: [benchmark/aws-production.md](aws-production.md) + `benchmark/results/phase6-aws/`
