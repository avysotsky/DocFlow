#!/usr/bin/env bash
set -euo pipefail

base_url="${DOCFLOW_BASE_URL:-http://127.0.0.1:5080}"
api_key="${DOCFLOW_API_KEY:-docflow-e2e-primary-key}"
customer_id="${DOCFLOW_CUSTOMER_ID:-11111111-1111-1111-1111-111111111111}"
storage_root="${FileStorage__RootPath:-/tmp/docflow-recovery-storage}"

uploaded_document_id='55555555-5555-5555-5555-555555555551'
processing_document_id='55555555-5555-5555-5555-555555555552'
other_fixture_document_id='44444444-4444-4444-4444-444444444445'
api_pid=''

psql_cmd() {
  docker run --rm --network host \
    -e PGPASSWORD=postgres \
    postgres:16 \
    psql -h 127.0.0.1 -U postgres -d docflow -v ON_ERROR_STOP=1 "$@"
}

stop_api() {
  if [ -n "${api_pid:-}" ]; then
    kill "$api_pid" 2>/dev/null || true
    wait "$api_pid" 2>/dev/null || true
    api_pid=''
  fi
}

start_api() {
  : > /tmp/docflow-recovery-api.log

  dotnet run \
    --project src/DocFlow.Api/DocFlow.Api.csproj \
    --configuration Release \
    --no-build \
    --no-launch-profile \
    > /tmp/docflow-recovery-api.log 2>&1 &
  api_pid=$!

  local ready=false
  for _ in $(seq 1 30); do
    if curl -fsS "$base_url/swagger/v1/swagger.json" >/dev/null 2>&1; then
      ready=true
      break
    fi

    if ! kill -0 "$api_pid" 2>/dev/null; then
      break
    fi

    sleep 1
  done

  if [ "$ready" != "true" ]; then
    cat /tmp/docflow-recovery-api.log
    echo "Recovery-test API did not become ready."
    exit 1
  fi
}

wait_for_status() {
  local document_id="$1"
  local expected_status="$2"
  local status=''

  for _ in $(seq 1 30); do
    local document_json
    document_json=$(curl -fsS \
      -H "X-DocFlow-Api-Key: $api_key" \
      "$base_url/api/documents/$document_id")
    status=$(printf '%s' "$document_json" | jq -r '.status')

    if [ "$status" = "$expected_status" ]; then
      return 0
    fi

    if [ "$status" = 'Failed' ] || [ "$status" = 'NeedsReview' ]; then
      break
    fi

    sleep 1
  done

  cat /tmp/docflow-recovery-api.log
  echo "Document $document_id did not reach $expected_status; last status: $status"
  return 1
}

cleanup() {
  stop_api
}
trap cleanup EXIT

rm -rf "$storage_root"
mkdir -p "$storage_root/recovery"

# Scenario 8 in the main E2E deliberately leaves one other-tenant Uploaded fixture
# without a file. Remove it so this restart test has exactly the two intended
# recovery candidates.
psql_cmd -c \
  "DELETE FROM \"Documents\" WHERE \"Id\" = '$other_fixture_document_id';"

# Start and stop one healthy host first so the next launch is a genuine restart.
start_api

processed_invoice_id=$(psql_cmd -At -c \
  "SELECT \"Id\" FROM \"Documents\" WHERE \"CustomerId\" = '$customer_id' AND \"OriginalFileName\" = 'supplier-invoice.pdf' AND \"Status\" = 'Processed' ORDER BY \"CreatedAt\" DESC LIMIT 1;")
test -n "$processed_invoice_id"

processed_attempts_before=$(curl -fsS \
  -H "X-DocFlow-Api-Key: $api_key" \
  "$base_url/api/documents/$processed_invoice_id/processing-diagnostics" \
  | jq -r '.processingAttempts')
test "$processed_attempts_before" = '1'

stop_api

cp /tmp/supplier-invoice.pdf "$storage_root/recovery/uploaded.pdf"
cp /tmp/supplier-invoice.pdf "$storage_root/recovery/processing.pdf"

psql_cmd -c \
  "DELETE FROM \"Documents\" WHERE \"Id\" IN ('$uploaded_document_id', '$processing_document_id');"

psql_cmd -c \
  "INSERT INTO \"Documents\" (\"Id\", \"CustomerId\", \"OriginalFileName\", \"ContentType\", \"StorageKey\", \"Size\", \"Status\", \"CreatedAt\") VALUES ('$uploaded_document_id', '$customer_id', 'restart-uploaded.pdf', 'application/pdf', 'recovery/uploaded.pdf', 1, 'Uploaded', NOW());"

psql_cmd -c \
  "INSERT INTO \"Documents\" (\"Id\", \"CustomerId\", \"OriginalFileName\", \"ContentType\", \"StorageKey\", \"Size\", \"Status\", \"CreatedAt\", \"ProcessingAttempts\", \"LastProcessingAttemptAt\") VALUES ('$processing_document_id', '$customer_id', 'restart-processing.pdf', 'application/pdf', 'recovery/processing.pdf', 1, 'Processing', NOW(), 1, NOW());"

# No enqueue API call is made. The second host must discover both persisted rows
# during startup and place them back onto the in-memory processing queue.
start_api

wait_for_status "$uploaded_document_id" 'Processed'
wait_for_status "$processing_document_id" 'Processed'

uploaded_diagnostics=$(curl -fsS \
  -H "X-DocFlow-Api-Key: $api_key" \
  "$base_url/api/documents/$uploaded_document_id/processing-diagnostics")
processing_diagnostics=$(curl -fsS \
  -H "X-DocFlow-Api-Key: $api_key" \
  "$base_url/api/documents/$processing_document_id/processing-diagnostics")

printf '%s' "$uploaded_diagnostics" | jq -e '
  .status == "Processed"
  and .processingAttempts == 1
  and .lastProcessingAttemptAt != null
  and .lastProcessingFailureAt == null
  and .lastProcessingError == null
' >/dev/null

printf '%s' "$processing_diagnostics" | jq -e '
  .status == "Processed"
  and .processingAttempts == 2
  and .lastProcessingAttemptAt != null
  and .lastProcessingFailureAt == null
  and .lastProcessingError == null
' >/dev/null

processed_attempts_after=$(curl -fsS \
  -H "X-DocFlow-Api-Key: $api_key" \
  "$base_url/api/documents/$processed_invoice_id/processing-diagnostics" \
  | jq -r '.processingAttempts')
test "$processed_attempts_after" = "$processed_attempts_before"

recovery_result_count=$(psql_cmd -At -c \
  "SELECT COUNT(*) FROM \"ExtractionResults\" WHERE \"DocumentId\" IN ('$uploaded_document_id', '$processing_document_id');")
test "$recovery_result_count" = '2'

echo "Restart recovery E2E passed: Uploaded and orphaned Processing work recovered after host restart without reprocessing completed documents."
