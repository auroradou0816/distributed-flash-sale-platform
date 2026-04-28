# Phase 0 Baseline Benchmark

## Benchmark Scope

- 目标接口：`POST /voucher-order/seckill/10`
- 并发模型：1000 个并发用户，每个用户 1 次秒杀请求
- 券与库存：`voucher_id=10`，初始库存 `100`
- 基线架构：保持当前实现不变，仍为 `Lua -> Redis Stream -> VoucherOrderHandler -> MySQL`
- 压测日期：2026-04-16

## Hardware Specs

- 机器：MacBook Pro (`Mac15,6`)
- CPU：Apple M3 Pro，11 cores（5P + 6E）
- RAM：18 GB
- OS：macOS 15.1.1 (24B91)
- Java：OpenJDK 17.0.18

## Redis / MySQL Config

- MySQL：Homebrew `mysql@8.0`，版本 `8.0.45`，`127.0.0.1:3306/flash_sale`
- Redis：Homebrew `redis`，版本 `8.6.2`，`127.0.0.1:6380`，无密码
- Redis 配置文件：`benchmark/redis-local.conf`
- 数据初始化：`src/main/resources/db/schema.sql`
- Benchmark profile：`src/test/resources/application-benchmark.yaml`

说明：

- 本地没有可直接使用的 MySQL 5.7 运行时，因此 Phase 0 基线使用了本机可稳定启动的 MySQL 8.0.45。
- 本机 `6379` 端口被 Docker Desktop 占用，因此本地 Redis 改为 `6380`。
- 以上偏差只影响本地基础设施版本，不改变当前业务链路，基线代码仍然是 Redis Stream 版本。

## Reproducible Commands

```bash
bash benchmark/init_local_env.sh
/opt/homebrew/opt/redis/bin/redis-server benchmark/redis-local.conf
JAVA_HOME=/Library/Java/JavaVirtualMachines/openjdk-17.jdk/Contents/Home mvn -q -DskipTests test-compile
JAVA_HOME=/Library/Java/JavaVirtualMachines/openjdk-17.jdk/Contents/Home mvn -q -DincludeScope=test -Dmdep.outputFile=target/benchmark.classpath dependency:build-classpath
JAVA_HOME=/Library/Java/JavaVirtualMachines/openjdk-17.jdk/Contents/Home java -cp "target/test-classes:target/classes:$(cat target/benchmark.classpath)" com.hmdp.BenchmarkHmDianPingApplication --spring.profiles.active=benchmark
bash benchmark/run_baseline.sh
```

## 3-Round Results

| Round | QPS | P50 (ms) | P95 (ms) | P99 (ms) | Error Rate | Order Consistency Check |
|---|---:|---:|---:|---:|---:|---|
| 1 | 1285.35 | 94.00 | 318.00 | 351.00 | 0.00% | PASS (`100` orders, DB stock `0`, Redis stock `0`) |
| 2 | 1148.11 | 4.00 | 222.00 | 266.00 | 0.00% | PASS (`100` orders, DB stock `0`, Redis stock `0`) |
| 3 | 1137.66 | 3.00 | 55.00 | 69.02 | 0.00% | PASS (`100` orders, DB stock `0`, Redis stock `0`) |
| Avg | 1190.37 | 33.67 | 198.33 | 228.67 | 0.00% | PASS (`3/3` rounds consistent) |

## Consistency Notes

- 三轮压测后，`tb_voucher_order` 均为 `100` 条，`tb_seckill_voucher.stock` 均为 `0`，与 Redis 库存扣减一致。
- 每轮 Redis `pending_messages=100`。这是当前基线代码里的遗留行为：消费者读取的是 `stream.orders`，但 `XACK` 使用的是 `"s1"`，所以消息会留在 pending-list。
- 该问题没有影响本次基线统计里的“下单成功数 == 库存扣减数”，但需要在后续架构升级阶段一并淘汰或修正。
