# AWS Deployment — hm-dianping Phase 5

End-to-end recipe for deploying hm-dianping (Spring Boot + MySQL + Redis + RocketMQ) to AWS. Verified reproducible on region `us-east-1`, 2026-04-16.

All commands below run from the repo root on a laptop with `awscli` v2 and Docker (with buildx) installed. Real resource IDs live in `aws-notes/resources.txt` (gitignored). The doc uses shell variables throughout so you can copy sections verbatim.

---

## 1. Target architecture

```
                        ┌──────────────────────────┐
                        │    Laptop (JMeter / curl) │
                        └───────────────┬───────────┘
                                        │  public internet
                                        ▼
         ┌───────────────── VPC 10.0.0.0/16 (2 AZs) ─────────────────┐
         │                                                           │
         │   public subnets (a / b)                                  │
         │   ┌──────────────────┐       ┌──────────────────┐         │
         │   │ hmdp-app-host    │──────▶│ hmdp-rmq-host    │  9876   │
         │   │ t3.small         │ 10911 │ RocketMQ         │         │
         │   │ docker: hmdp-app │       │ namesrv + broker │         │
         │   └────────┬─────────┘       └──────────────────┘         │
         │            │ 3306            │ 6379                       │
         │            ▼                 ▼                            │
         │   private subnets (a / b)                                 │
         │   ┌──────────────────┐   ┌──────────────────┐             │
         │   │ RDS MySQL 8.0    │   │ ElastiCache      │             │
         │   │ db.t3.micro      │   │ Redis 7.x        │             │
         │   │ (private)        │   │ cache.t3.micro   │             │
         │   └──────────────────┘   └──────────────────┘             │
         └───────────────────────────────────────────────────────────┘
```

SG traffic matrix:

| From       | To       | Port        | Purpose            |
|------------|----------|-------------|--------------------|
| my IP      | APP_SG   | 22, 8081    | SSH + app          |
| my IP      | RMQ_SG   | 22          | SSH only           |
| APP_SG     | RDS_SG   | 3306        | JDBC               |
| APP_SG     | REDIS_SG | 6379        | Lettuce            |
| APP_SG     | RMQ_SG   | 9876, 10911 | namesrv + broker   |

---

## 2. Prerequisites

- AWS account with IAM user that has EC2/VPC/RDS/ElastiCache/ECR permissions.
  `iam:*` is **not** required if you skip the EC2 instance profile (see §5.1).
  `ssm:GetParameters` is **not** required if you use `ec2 describe-images` for AMI lookup (see §5.1).
- Local: awscli v2, Docker Desktop with `buildx`, `mysql` client, JMeter (for Phase 6).
- `aws configure` done, `export AWS_PAGER=""` in the current shell.
- `setopt interactive_comments` if using zsh and pasting `#`-commented blocks.

---

## 3. Build and push image (Phase 4 + 5a recap)

App is packaged as a linux/amd64 image via buildx (Apple Silicon hosts otherwise produce arm64, which EC2 rejects with `exec format error`).

```bash
./mvnw -DskipTests package
./scripts/deploy.sh           # builds amd64 + pushes to ECR
```

`scripts/deploy.sh` does:

```bash
docker buildx create --use --name hmdp-builder 2>/dev/null || docker buildx use hmdp-builder
docker buildx build --platform linux/amd64 \
  -t "${ECR_REPO}:${IMAGE_TAG}" --load .
aws ecr get-login-password --region us-east-1 | \
  docker login --username AWS --password-stdin "$ECR_REGISTRY"
docker push "${ECR_REPO}:${IMAGE_TAG}"
```

Verify:

```bash
aws ecr describe-images --repository-name hmdp-dianping \
  --query 'sort_by(imageDetails,&imagePushedAt)[-1].{Tags:imageTags,Size:imageSizeInBytes}'
```

---

## 4. Provision network, SGs, data stores (Phase 5b–5c)

Use separate terminal sessions or source `aws-notes/resources.txt` to re-hydrate variables.

### 4.1 VPC + 4 subnets + IGW + routes

```bash
MY_IP=$(curl -s https://checkip.amazonaws.com)/32

VPC_ID=$(aws ec2 create-vpc --cidr-block 10.0.0.0/16 \
  --query Vpc.VpcId --output text)
aws ec2 modify-vpc-attribute --vpc-id $VPC_ID --enable-dns-hostnames

PUB_SUBNET_A=$(aws ec2 create-subnet --vpc-id $VPC_ID \
  --cidr-block 10.0.1.0/24 --availability-zone us-east-1a \
  --query Subnet.SubnetId --output text)
PUB_SUBNET_B=$(aws ec2 create-subnet --vpc-id $VPC_ID \
  --cidr-block 10.0.2.0/24 --availability-zone us-east-1b \
  --query Subnet.SubnetId --output text)
PRIV_SUBNET_A=$(aws ec2 create-subnet --vpc-id $VPC_ID \
  --cidr-block 10.0.11.0/24 --availability-zone us-east-1a \
  --query Subnet.SubnetId --output text)
PRIV_SUBNET_B=$(aws ec2 create-subnet --vpc-id $VPC_ID \
  --cidr-block 10.0.12.0/24 --availability-zone us-east-1b \
  --query Subnet.SubnetId --output text)

IGW_ID=$(aws ec2 create-internet-gateway \
  --query InternetGateway.InternetGatewayId --output text)
aws ec2 attach-internet-gateway --internet-gateway-id $IGW_ID --vpc-id $VPC_ID

PUB_RT=$(aws ec2 create-route-table --vpc-id $VPC_ID \
  --query RouteTable.RouteTableId --output text)
aws ec2 create-route --route-table-id $PUB_RT \
  --destination-cidr-block 0.0.0.0/0 --gateway-id $IGW_ID
aws ec2 associate-route-table --route-table-id $PUB_RT --subnet-id $PUB_SUBNET_A
aws ec2 associate-route-table --route-table-id $PUB_RT --subnet-id $PUB_SUBNET_B
```

### 4.2 Security groups

```bash
APP_SG=$(aws ec2 create-security-group --group-name hmdp-app-sg \
  --description "hmdp app" --vpc-id $VPC_ID --query GroupId --output text)
RMQ_SG=$(aws ec2 create-security-group --group-name hmdp-rmq-sg \
  --description "RocketMQ" --vpc-id $VPC_ID --query GroupId --output text)
RDS_SG=$(aws ec2 create-security-group --group-name hmdp-rds-sg \
  --description "RDS MySQL" --vpc-id $VPC_ID --query GroupId --output text)
REDIS_SG=$(aws ec2 create-security-group --group-name hmdp-redis-sg \
  --description "ElastiCache" --vpc-id $VPC_ID --query GroupId --output text)

# Laptop -> app
aws ec2 authorize-security-group-ingress --group-id $APP_SG \
  --protocol tcp --port 22 --cidr $MY_IP
aws ec2 authorize-security-group-ingress --group-id $APP_SG \
  --protocol tcp --port 8081 --cidr $MY_IP
aws ec2 authorize-security-group-ingress --group-id $RMQ_SG \
  --protocol tcp --port 22 --cidr $MY_IP

# App -> data plane (SG-to-SG, not CIDR)
aws ec2 authorize-security-group-ingress --group-id $RDS_SG \
  --protocol tcp --port 3306 --source-group $APP_SG
aws ec2 authorize-security-group-ingress --group-id $REDIS_SG \
  --protocol tcp --port 6379 --source-group $APP_SG
aws ec2 authorize-security-group-ingress --group-id $RMQ_SG \
  --protocol tcp --port 9876 --source-group $APP_SG
aws ec2 authorize-security-group-ingress --group-id $RMQ_SG \
  --protocol tcp --port 10911 --source-group $APP_SG
```

### 4.3 RDS MySQL

```bash
aws rds create-db-subnet-group --db-subnet-group-name hmdp-db-subnets \
  --db-subnet-group-description "hmdp private" \
  --subnet-ids $PRIV_SUBNET_A $PRIV_SUBNET_B

aws rds create-db-instance \
  --db-instance-identifier hmdp-mysql \
  --db-instance-class db.t3.micro \
  --engine mysql --engine-version 8.0.35 \
  --master-username hmdpadmin \
  --master-user-password "$(openssl rand -base64 24 | tr -d '/+=')" \
  --allocated-storage 20 --storage-type gp2 \
  --vpc-security-group-ids $RDS_SG \
  --db-subnet-group-name hmdp-db-subnets \
  --no-publicly-accessible \
  --backup-retention-period 0
# Save the generated password to aws-notes/secrets.txt immediately.

aws rds wait db-instance-available --db-instance-identifier hmdp-mysql
DB_ENDPOINT=$(aws rds describe-db-instances --db-instance-identifier hmdp-mysql \
  --query 'DBInstances[0].Endpoint.Address' --output text)
```

### 4.4 ElastiCache Redis

```bash
aws elasticache create-cache-subnet-group \
  --cache-subnet-group-name hmdp-redis-subnets \
  --cache-subnet-group-description "hmdp private" \
  --subnet-ids $PRIV_SUBNET_A $PRIV_SUBNET_B

aws elasticache create-cache-cluster \
  --cache-cluster-id hmdp-redis \
  --engine redis --cache-node-type cache.t3.micro \
  --num-cache-nodes 1 \
  --security-group-ids $REDIS_SG \
  --cache-subnet-group-name hmdp-redis-subnets

aws elasticache wait cache-cluster-available --cache-cluster-id hmdp-redis
REDIS_ENDPOINT=$(aws elasticache describe-cache-clusters \
  --cache-cluster-id hmdp-redis --show-cache-node-info \
  --query 'CacheClusters[0].CacheNodes[0].Endpoint.Address' --output text)
```

---

## 5. Launch EC2 hosts (Phase 5d.1)

### 5.1 AMI lookup without SSM

SSM gives the canonical pointer but requires `ssm:GetParameters`. Fall back to `ec2 describe-images`:

```bash
AMI_ID=$(aws ec2 describe-images --owners amazon \
  --filters "Name=name,Values=al2023-ami-*-kernel-*-x86_64" \
            "Name=state,Values=available" \
            "Name=architecture,Values=x86_64" \
            "Name=virtualization-type,Values=hvm" \
  --query 'sort_by(Images, &CreationDate)[-1].ImageId' --output text)
```

### 5.2 Key pair + instances

```bash
aws ec2 create-key-pair --key-name hmdp-keypair --key-type rsa \
  --query KeyMaterial --output text > ~/.ssh/hmdp-keypair.pem
chmod 400 ~/.ssh/hmdp-keypair.pem

# AL2023 snapshot floor = 30 GB. Do NOT use 10/20 GB.
APP_INSTANCE=$(aws ec2 run-instances \
  --image-id $AMI_ID --instance-type t3.small \
  --key-name hmdp-keypair \
  --security-group-ids $APP_SG --subnet-id $PUB_SUBNET_A \
  --associate-public-ip-address \
  --block-device-mappings 'DeviceName=/dev/xvda,Ebs={VolumeSize=30,VolumeType=gp3}' \
  --tag-specifications 'ResourceType=instance,Tags=[{Key=Name,Value=hmdp-app-host}]' \
  --query 'Instances[0].InstanceId' --output text)

RMQ_INSTANCE=$(aws ec2 run-instances \
  --image-id $AMI_ID --instance-type t3.small \
  --key-name hmdp-keypair \
  --security-group-ids $RMQ_SG --subnet-id $PUB_SUBNET_A \
  --associate-public-ip-address \
  --block-device-mappings 'DeviceName=/dev/xvda,Ebs={VolumeSize=30,VolumeType=gp3}' \
  --tag-specifications 'ResourceType=instance,Tags=[{Key=Name,Value=hmdp-rmq-host}]' \
  --query 'Instances[0].InstanceId' --output text)

aws ec2 wait instance-running --instance-ids $APP_INSTANCE $RMQ_INSTANCE

APP_PUBLIC_IP=$(aws ec2 describe-instances --instance-ids $APP_INSTANCE \
  --query 'Reservations[0].Instances[0].PublicIpAddress' --output text)
RMQ_PUBLIC_IP=$(aws ec2 describe-instances --instance-ids $RMQ_INSTANCE \
  --query 'Reservations[0].Instances[0].PublicIpAddress' --output text)
RMQ_PRIVATE_IP=$(aws ec2 describe-instances --instance-ids $RMQ_INSTANCE \
  --query 'Reservations[0].Instances[0].PrivateIpAddress' --output text)
```

> Optional `--iam-instance-profile Name=hmdp-ec2-profile` lets the app-host pull from ECR via instance metadata instead of a laptop-generated token. Requires `iam:CreateInstanceProfile` + `iam:AddRoleToInstanceProfile` on the caller. If those aren't granted, omit the flag and use the 12-hour ECR token flow in §7.

---

## 6. Bring up RocketMQ on rmq-host (Phase 5d.2)

```bash
ssh -i ~/.ssh/hmdp-keypair.pem ec2-user@$RMQ_PUBLIC_IP bash <<EOF
sudo dnf install -y docker
sudo systemctl enable --now docker
mkdir -p ~/rocketmq/conf

cat > ~/rocketmq/conf/broker.conf <<CONF
brokerClusterName=DefaultCluster
brokerName=broker-a
brokerId=0
deleteWhen=04
fileReservedTime=48
brokerRole=ASYNC_MASTER
flushDiskType=ASYNC_FLUSH
autoCreateTopicEnable=true
brokerIP1=$RMQ_PRIVATE_IP
namesrvAddr=$RMQ_PRIVATE_IP:9876
diskMaxUsedSpaceRatio=85
CONF

sudo docker run -d --name rmqnamesrv -p 9876:9876 \
  -e "JAVA_OPT_EXT=-Xms512m -Xmx512m -Xmn256m" \
  apache/rocketmq:5.1.4 sh mqnamesrv

sleep 5

sudo docker run -d --name rmqbroker \
  -p 10911:10911 -p 10909:10909 -p 10912:10912 \
  -v ~/rocketmq/conf/broker.conf:/home/rocketmq/rocketmq-5.1.4/conf/broker.conf \
  -e "JAVA_OPT_EXT=-Xms1g -Xmx1g -Xmn512m" \
  apache/rocketmq:5.1.4 sh mqbroker -c /home/rocketmq/rocketmq-5.1.4/conf/broker.conf
EOF
```

Two gotchas:
- **Do not** bind-mount `~/rocketmq/store` or `~/rocketmq/logs` from host — the container user (uid 3000) cannot write to host dirs owned by ec2-user and the broker crashes with an NPE during shutdown cleanup.
- `diskMaxUsedSpaceRatio=85` raises the broker's self-protection threshold from the default 75%. On a 30 GB root disk with AL2023 the default often trips during smoke tests.

Success line to grep for in `docker logs rmqbroker`:
```
The broker[broker-a, <RMQ_PRIVATE_IP>:10911] boot success
```

---

## 7. Seed DB and run app (Phase 5d.3 + 5d.4)

### 7.1 Seed schema

```bash
scp -i ~/.ssh/hmdp-keypair.pem \
  src/main/resources/db/hmdp.sql \
  src/main/resources/db/migration/V2__add_voucher_order_unique.sql \
  ec2-user@$APP_PUBLIC_IP:~/

ssh -i ~/.ssh/hmdp-keypair.pem ec2-user@$APP_PUBLIC_IP bash <<EOF
sudo dnf install -y docker mariadb105
sudo systemctl enable --now docker

export MYSQL_PWD='<DB_ADMIN_PASSWORD>'
mysql -h $DB_ENDPOINT -u hmdpadmin \
  -e 'CREATE DATABASE IF NOT EXISTS hmdp DEFAULT CHARSET utf8mb4;'
mysql -h $DB_ENDPOINT -u hmdpadmin hmdp < ~/hmdp.sql
mysql -h $DB_ENDPOINT -u hmdpadmin hmdp < ~/V2__add_voucher_order_unique.sql
EOF
```

### 7.2 Run container

```bash
ECR_REGISTRY=<account-id>.dkr.ecr.us-east-1.amazonaws.com
ECR_TOKEN=$(aws ecr get-login-password --region us-east-1)

ssh -i ~/.ssh/hmdp-keypair.pem ec2-user@$APP_PUBLIC_IP bash <<EOF
echo '$ECR_TOKEN' | sudo docker login --username AWS --password-stdin $ECR_REGISTRY
sudo docker pull $ECR_REGISTRY/hmdp-dianping:latest

sudo docker run -d --name hmdp-app -p 8081:8081 --restart unless-stopped \
  -e DB_HOST=$DB_ENDPOINT \
  -e DB_USER=hmdpadmin \
  -e DB_PASSWORD='<DB_ADMIN_PASSWORD>' \
  -e DB_NAME=hmdp \
  -e REDIS_HOST=$REDIS_ENDPOINT \
  -e MQ_NAME_SERVER=$RMQ_PRIVATE_IP:9876 \
  $ECR_REGISTRY/hmdp-dianping:latest
EOF
```

The ECR login token is valid 12 hours. Re-run `aws ecr get-login-password` + `docker login` on expiry.

---

## 8. Smoke test (Phase 5d.5)

`/shop-type/**`, `/shop/**`, `/voucher/**` are public paths (see `config/MvcConfig.java`). No `/api` prefix in the backend — that's added by the nginx frontend in the original stack.

```bash
for path in /shop-type/list /shop/1 /voucher/list/1; do
  echo "=== $path ==="
  curl -sS -w "\nHTTP %{http_code}  time %{time_total}s\n" \
    "http://$APP_PUBLIC_IP:8081$path" | head -c 400; echo
done
```

Expected: all three return `HTTP 200` + JSON `{"success":true,"data":...}`.

---

## 9. Teardown (stop billing)

Run from laptop after sourcing `aws-notes/resources.txt`. **Order matters** — SGs can't be deleted while anything references them.

```bash
# 1. Stop compute
aws ec2 terminate-instances --instance-ids $APP_INSTANCE $RMQ_INSTANCE
aws ec2 wait instance-terminated --instance-ids $APP_INSTANCE $RMQ_INSTANCE

# 2. Data stores (slow — ~5-10 min each)
aws rds delete-db-instance --db-instance-identifier hmdp-mysql \
  --skip-final-snapshot --delete-automated-backups
aws elasticache delete-cache-cluster --cache-cluster-id hmdp-redis
aws rds wait db-instance-deleted --db-instance-identifier hmdp-mysql
aws elasticache wait cache-cluster-deleted --cache-cluster-id hmdp-redis

aws rds delete-db-subnet-group --db-subnet-group-name hmdp-db-subnets
aws elasticache delete-cache-subnet-group --cache-subnet-group-name hmdp-redis-subnets

# 3. Network plumbing
for sg in $APP_SG $RMQ_SG $RDS_SG $REDIS_SG; do
  aws ec2 delete-security-group --group-id $sg
done
aws ec2 detach-internet-gateway --internet-gateway-id $IGW_ID --vpc-id $VPC_ID
aws ec2 delete-internet-gateway --internet-gateway-id $IGW_ID
for subnet in $PUB_SUBNET_A $PUB_SUBNET_B $PRIV_SUBNET_A $PRIV_SUBNET_B; do
  aws ec2 delete-subnet --subnet-id $subnet
done
aws ec2 delete-route-table --route-table-id $PUB_RT
aws ec2 delete-vpc --vpc-id $VPC_ID

# 4. ECR (optional — keeps repo for next deploy)
# aws ecr delete-repository --repository-name hmdp-dianping --force
```

---

## 10. Gotchas encountered during the first deploy

| Symptom | Cause | Fix |
|---|---|---|
| `exec format error` on EC2 | arm64 image on amd64 host | `docker buildx build --platform linux/amd64` |
| `Value (…) for iamInstanceProfile.name is invalid` | instance profile missing or not propagated | Skip profile + use laptop-generated ECR token (§5.2 note) |
| `Volume of size 20GB is smaller than snapshot` | AL2023 floor is 30 GB | `VolumeSize=30` in block-device-mappings |
| Broker NPE during cleanup | host volume mount permissions (uid 3000 vs ec2-user) | Drop `-v ~/rocketmq/store` and `-v ~/rocketmq/logs` |
| Broker refuses to accept messages | `diskMaxUsedSpaceRatio` default 75% tripped | Set to 85 in `broker.conf` |
| `User: mydp is not authorized to perform: ssm:GetParameters` | IAM user lacks SSM | Use `ec2 describe-images` (§5.1) |
| `Access denied for user 'admin'@...` | RDS master user is `hmdpadmin`, not `admin` | `describe-db-instances` to confirm `MasterUsername` |
| HTTP 401 on public endpoints | URL has `/api/` prefix | Drop `/api/` — backend routes are unprefixed (nginx adds it) |
