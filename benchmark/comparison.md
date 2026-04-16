# Phase 0 vs Phase 3 Comparison

## Side-by-Side Table

| Metric | Phase 0 (Redis Stream) | Phase 3 (RocketMQ + Idempotent Consumer) | Delta |
|---|---:|---:|---:|
| QPS | 1190.37 | 1181.05 | -0.78% |
| P50 (ms) | 33.67 | 18.00 | -46.54% |
| P95 (ms) | 198.33 | 152.68 | -23.02% |
| P99 (ms) | 228.67 | 181.34 | -20.70% |
| Error rate | 0.00% | 0.00% | 0.00% |

## Honest Readout

- 本次本机 steady-state 结果里，RocketMQ 版本的**吞吐上限基本持平**，平均 QPS 从 `1190.37` 到 `1181.05`，变化只有 `-0.78%`
- 这 3 轮本地结果里，RocketMQ 版本的尾延迟反而更好，平均 `P99` 从 `228.67 ms` 降到 `181.34 ms`，但这应当被理解为**本机实测结果**，而不是“换成 MQ 天然就更快”
- 真正确定性的架构收益不在于单机延迟数字，而在于：
  - Redis Stream 单线程后台消费被替换成 RocketMQ consumer group，可水平扩展
  - 消费语义从“项目内自维护轮询 + pending-list 遗留问题”升级为标准 ack / retry / consumer progress
  - Phase 2 的 DB 唯一索引 `uk_user_voucher` + `DuplicateKeyException` fast-ack 已经把重复投递幂等补齐
- 对比 Phase 0，Redis Stream 版本每轮都会留下 `pending_messages=100` 的遗留 pending-list；Phase 3 则在 3 轮里都实现了 `Consume Diff Total = 0`、`Consume Inflight Total = 0`
- 需要单独说明的是：RocketMQ fresh broker 启动后的第一条消息有明显冷启动延迟，所以本次表格反映的是**warm steady-state**，不代表 RocketMQ 冷启动首条消息体验

## ASCII Snapshot

```text
QPS   Redis Stream  1190.37 | RocketMQ 1181.05
P99   Redis Stream   228.67 | RocketMQ  181.34
Error Redis Stream     0.00 | RocketMQ    0.00
```

## PNG Placeholder

- 后续如果需要放到 README / 简历截图里，可以把上表生成一张并排柱状图 PNG；当前所有数字都以 `benchmark/baseline.md` 和 `benchmark/after-rocketmq.md` 的实测均值为准
