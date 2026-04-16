#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
RESULT_DIR="${ROOT_DIR}/benchmark/results"
TOKEN_FILE="${TOKEN_FILE:-${ROOT_DIR}/benchmark/data/tokens.txt}"
PYTHON_BIN="${PYTHON_BIN:-${ROOT_DIR}/benchmark/.venv/bin/python}"
ROUNDS="${ROUNDS:-3}"
THREADS="${THREADS:-1000}"
RAMP_UP_SECONDS="${RAMP_UP_SECONDS:-1}"
APP_BASE_URL="${APP_BASE_URL:-http://127.0.0.1:8081}"
HOST="${BENCHMARK_HOST:-127.0.0.1}"
PORT="${BENCHMARK_PORT:-8081}"
VOUCHER_ID="${VOUCHER_ID:-10}"
EXPECTED_ORDERS="${EXPECTED_ORDERS:-100}"
STOCK="${BENCHMARK_STOCK:-100}"

mkdir -p "${RESULT_DIR}" "$(dirname "${TOKEN_FILE}")"

"${PYTHON_BIN}" "${ROOT_DIR}/benchmark/prepare_tokens.py" --output "${TOKEN_FILE}" --base-url "${APP_BASE_URL}"

for round in $(seq 1 "${ROUNDS}"); do
  echo "Running baseline round ${round}/${ROUNDS} ..."
  "${PYTHON_BIN}" "${ROOT_DIR}/benchmark/reset_state.py" --voucher-id "${VOUCHER_ID}" --stock "${STOCK}" > "${RESULT_DIR}/round-${round}-reset.json"

  jmeter -n \
    -t "${ROOT_DIR}/benchmark/seckill-baseline.jmx" \
    -l "${RESULT_DIR}/round-${round}.jtl" \
    -j "${RESULT_DIR}/round-${round}.log" \
    -Jhost="${HOST}" \
    -Jport="${PORT}" \
    -Jprotocol=http \
    -JvoucherId="${VOUCHER_ID}" \
    -JtokensFile="${TOKEN_FILE}" \
    -JthreadCount="${THREADS}" \
    -JrampUpSeconds="${RAMP_UP_SECONDS}" \
    -Jjmeter.save.saveservice.output_format=csv \
    -Jjmeter.save.saveservice.timestamp_format=ms \
    -Jjmeter.save.saveservice.print_field_names=true \
    -Jjmeter.save.saveservice.time=true \
    -Jjmeter.save.saveservice.timestamp=true \
    -Jjmeter.save.saveservice.successful=true \
    -Jjmeter.save.saveservice.label=true \
    -Jjmeter.save.saveservice.code=true \
    -Jjmeter.save.saveservice.message=true \
    -Jjmeter.save.saveservice.thread_name=true \
    -Jjmeter.save.saveservice.data_type=true \
    -Jjmeter.save.saveservice.connect_time=true \
    -Jjmeter.save.saveservice.latency=true \
    -Jjmeter.save.saveservice.subresults=false \
    -Jjmeter.save.saveservice.assertion_results=none \
    -Jjmeter.save.saveservice.response_data=false \
    -Jjmeter.save.saveservice.samplerData=false \
    -Jjmeter.save.saveservice.requestHeaders=false \
    -Jjmeter.save.saveservice.responseHeaders=false \
    -Jjmeter.save.saveservice.bytes=true \
    -Jjmeter.save.saveservice.sent_bytes=true \
    -Jjmeter.save.saveservice.url=true \
    -Jjmeter.save.saveservice.thread_counts=true \
    -Jjmeter.save.saveservice.idle_time=true

  "${PYTHON_BIN}" "${ROOT_DIR}/benchmark/summarize_jtl.py" --jtl "${RESULT_DIR}/round-${round}.jtl" > "${RESULT_DIR}/round-${round}-summary.json"
  "${PYTHON_BIN}" "${ROOT_DIR}/benchmark/check_consistency.py" --voucher-id "${VOUCHER_ID}" --expected-orders "${EXPECTED_ORDERS}" --initial-stock "${STOCK}" > "${RESULT_DIR}/round-${round}-consistency.json"
done

"${PYTHON_BIN}" "${ROOT_DIR}/benchmark/aggregate_summaries.py" "${RESULT_DIR}"/round-*-summary.json > "${RESULT_DIR}/average-summary.json"
echo "Baseline benchmark completed. Summaries saved to ${RESULT_DIR}."
