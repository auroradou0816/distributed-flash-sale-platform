# Phase 3 Post-Change Benchmark (Local RocketMQ)

## Benchmark Scope

- 目标接口：`POST /voucher-order/seckill/10`
- 并发模型：1000 个并发用户，每个用户 1 次秒杀请求
- 券与库存：`voucher_id=10`，初始库存 `100`
- 测量架构：`Lua -> RocketMQ -> SeckillOrderConsumer -> MySQL`
- 被测应用提交：`e4041cf`（从该提交拉出 clean worktree `/tmp/hmdp-phase3-clean` 后构建，避免工作区其他脏文件污染本次测量）
- 压测日期：2026-04-16

## Hardware Specs

- 机器：MacBook Pro (`Mac15,6`)
- CPU：Apple M3 Pro，11 cores（5P + 6E）
- RAM：18 GB
- OS：macOS 15.1.1 (24B91)
- 应用 JVM：OpenJDK 17.0.18

## MySQL / Redis / RocketMQ Config

- MySQL：Homebrew `mysql@8.0`，版本 `8.0.45`，`127.0.0.1:3306/hmdp`
- Redis：Homebrew `redis`，版本 `8.6.2`，`127.0.0.1:6380`，无密码
- Redis 配置文件：`benchmark/redis-local.conf`
- RocketMQ：本地二进制 `5.1.4`
- NameServer：`127.0.0.1:9876`
- Broker：`127.0.0.1:10911`
- Broker 配置：`docker/rocketmq/broker.conf`
- 关键 Broker 参数：
  - `brokerIP1=localhost`
  - `JAVA_OPT_EXT=-Xms512m -Xmx512m`
- Topic hygiene 策略：
  - 本次没有复用旧 broker store，而是用 fresh store 目录 `/tmp/hmdp-rmq-home-phase3/store`
  - 这样可以直接隔离掉之前开发过程中的历史消息、offset、`%RETRY%seckill-order-consumer-group` backlog
  - Broker 启动后额外发送了 1 条**不计入正式结果**的 warm-up 秒杀请求，用于触发 `seckill-order-topic` 自动创建和 consumer 首次 queue assignment

## Exact Commands Used

```bash
# 1) 准备 RocketMQ 5.1.4 本地二进制
mkdir -p /tmp/hmdp-rmq
cd /tmp/hmdp-rmq
curl -L -o rocketmq-all-5.1.4-bin-release.zip \
  https://archive.apache.org/dist/rocketmq/5.1.4/rocketmq-all-5.1.4-bin-release.zip
unzip -q rocketmq-all-5.1.4-bin-release.zip

# 2) 以 fresh store 目录启动 RocketMQ
rm -rf /tmp/hmdp-rmq-home-phase3
mkdir -p /tmp/hmdp-rmq-home-phase3
JAVA_HOME=/Library/Java/JavaVirtualMachines/amazon-corretto-11.jdk/Contents/Home \
  /tmp/hmdp-rmq/rocketmq-all-5.1.4-bin-release/bin/mqnamesrv
JAVA_HOME=/Library/Java/JavaVirtualMachines/amazon-corretto-11.jdk/Contents/Home \
JAVA_OPT_EXT='-Xms512m -Xmx512m -Duser.home=/tmp/hmdp-rmq-home-phase3' \
  /tmp/hmdp-rmq/rocketmq-all-5.1.4-bin-release/bin/mqbroker \
  -n localhost:9876 \
  -c /Users/ivy_dou/Documents/heimadianping/coding/hm-dianping/docker/rocketmq/broker.conf

# 3) 校验本地 MySQL / Redis / RocketMQ
mysql -uroot -e "SELECT VERSION();" hmdp
redis-cli -p 6380 PING
NAMESRV_ADDR=127.0.0.1:9876 \
  /tmp/hmdp-rmq/rocketmq-all-5.1.4-bin-release/bin/mqadmin clusterList -m -n 127.0.0.1:9876

# 4) 从 clean worktree 构建并启动应用
git worktree add --detach /tmp/hmdp-phase3-clean e4041cff3d20aaf177b7f89641fcab1d854a732f
cd /tmp/hmdp-phase3-clean
JAVA_HOME=$(/usr/libexec/java_home -v 17) mvn -DskipTests package
JAVA_HOME=$(/usr/libexec/java_home -v 17)
"$JAVA_HOME/bin/java" -jar /tmp/hmdp-phase3-clean/target/hm-dianping-0.0.1-SNAPSHOT.jar

# 5) 生成 1000 个登录 token
cd /Users/ivy_dou/Documents/heimadianping/coding/hm-dianping
benchmark/.venv/bin/python benchmark/prepare_tokens.py \
  --output benchmark/data/tokens.txt \
  --base-url http://127.0.0.1:8081

# 6) 每轮压测前 reset；JMeter 使用与 Phase 0 完全相同的 benchmark/seckill-baseline.jmx
benchmark/.venv/bin/python benchmark/reset_state.py --voucher-id 10 --stock 100
jmeter -n \
  -t benchmark/seckill-baseline.jmx \
  -l benchmark/results/phase3-rocketmq/round1/round1.jtl \
  -j benchmark/results/phase3-rocketmq/round1/round1.log \
  -Jhost=127.0.0.1 \
  -Jport=8081 \
  -Jprotocol=http \
  -JvoucherId=10 \
  -JtokensFile=benchmark/data/tokens.txt \
  -JthreadCount=1000 \
  -JrampUpSeconds=1 \
  ...（其余 save-service 参数与 benchmark/run_baseline.sh 完全一致）
```

## 3-Round Results

| Round | QPS | P50 (ms) | P95 (ms) | P99 (ms) | Error Rate | Consistency Check | MQ Backlog |
|---|---:|---:|---:|---:|---:|---|---|
| 1 | 1253.13 | 34.00 | 178.05 | 222.00 | 0.00% | PASS (`100` orders, DB stock `0`, Redis stock `0`) | PASS (`diff=0`, `inflight=0`) |
| 2 | 1129.94 | 17.00 | 140.00 | 150.00 | 0.00% | PASS (`100` orders, DB stock `0`, Redis stock `0`) | PASS (`diff=0`, `inflight=0`) |
| 3 | 1160.09 | 3.00 | 140.00 | 172.01 | 0.00% | PASS (`100` orders, DB stock `0`, Redis stock `0`) | PASS (`diff=0`, `inflight=0`) |
| Avg | 1181.05 | 18.00 | 152.68 | 181.34 | 0.00% | PASS (`3/3` rounds consistent) | PASS (`3/3` rounds drained) |

## Consistency Notes

- 每轮压测结束后，`tb_voucher_order` 均为 `100` 条，`tb_seckill_voucher.stock` 均为 `0`，Redis `seckill:stock:10` 也为 `0`
- `SeckillOrderConsumer` 消费完毕后，`mqadmin consumerProgress` 三轮均为 `Consume Diff Total = 0`、`Consume Inflight Total = 0`
- `%RETRY%seckill-order-consumer-group` topic 在 broker 内存在，但本次三轮没有遗留 retry backlog
- `check_consistency.py` 里的 `pending_messages` 字段是沿用 Phase 0 Redis Stream 检查逻辑的遗留字段；在 RocketMQ 版本下该字段恒为 `0`，真正的异步 backlog 以 `mqadmin consumerProgress` 为准

## Observed Anomalies

- RocketMQ fresh broker 启动后的**第一条**消息（不计入正式结果）出现了约 24 秒的消费冷启动延迟；根因更像是 `seckill-order-topic` 自动创建和 consumer 首次队列分配，而不是 steady-state 热路径吞吐
- 在做完 1 条 warm-up 后，正式 3 轮测量的 MQ backlog 都能清零，没有出现 retry storm 或持续堆积
- JMeter 运行时有 `package sun.awt.X11 not in java.desktop` 警告，但不影响结果文件生成或压测执行
