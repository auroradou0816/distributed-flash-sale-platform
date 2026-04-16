#!/usr/bin/env bash
set -euo pipefail

: "${ECR_REGISTRY:?ECR_REGISTRY env var required, e.g. 123456789012.dkr.ecr.us-east-1.amazonaws.com}"
: "${ECR_REPO:?ECR_REPO env var required, e.g. hm-dianping}"
: "${AWS_REGION:?AWS_REGION env var required, e.g. us-east-1}"

IMAGE_TAG="${IMAGE_TAG:-$(git rev-parse --short HEAD)}"

JAVA_HOME=$(/usr/libexec/java_home -v 17) mvn -DskipTests clean package

docker build -t "${ECR_REPO}:${IMAGE_TAG}" .

docker tag "${ECR_REPO}:${IMAGE_TAG}" "${ECR_REGISTRY}/${ECR_REPO}:${IMAGE_TAG}"
docker tag "${ECR_REPO}:${IMAGE_TAG}" "${ECR_REGISTRY}/${ECR_REPO}:latest"

aws ecr get-login-password --region "${AWS_REGION}" | \
  docker login --username AWS --password-stdin "${ECR_REGISTRY}"

docker push "${ECR_REGISTRY}/${ECR_REPO}:${IMAGE_TAG}"
docker push "${ECR_REGISTRY}/${ECR_REPO}:latest"

echo "Pushed ${ECR_REGISTRY}/${ECR_REPO}:${IMAGE_TAG}"
