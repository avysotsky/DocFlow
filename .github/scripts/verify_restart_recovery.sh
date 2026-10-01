#!/usr/bin/env bash
set -euo pipefail

base_url="${DOCFLOW_BASE_URL:-http://127.0.0.1:5080}"
api_key="${DOCFLOW_API_KEY:-docflow-e2e-primary-key}"
customer_id="${DOCFLOW_CUSTOMER_ID:-11111111-1111-1111-1111-111111111111}"
other_customer_id='44444444-4444-4444-4444-444444444444'
storage_root="${FileStorage__RootPath:-/tmp/docflow-recovery-storage}"

# The main Automation E2E step runs with repository defaults, so retention is disabled
# for those uploads. This restart/lifecycle step explicitly enables a fast test policy.
export Retention__Enabled="${Retention__Enabled:-true}"
export Retention__DefaultRetentionDays="${Retention__DefaultRetentionDays:-7}"
export Retention__SweepIntervalSeconds="${Retention__SweepIntervalSeconds:-1}"
export Retention__BatchSize="${Retention__BatchSize:-50}"

uploaded_document_id='55555555-5555-5555-5555-555555555551'
processing_document_id='55555555-5555-5555-5555-555555555552'
uploaded_conflict_document_id='55555555-5555-5555-5555-555555555553'
processing_conflict_document_id='55555555-5555-5555-5555-555555555554'
failed_delete_document_id='55555555-5555-5555-5555-555555555555'
review_id='55555555-5555-5555-5555-555555555556'
retention_expired_document_id='55555555-5555-5555-5555-555555555557'
retention_active_document_id='55555555-5555-5555-5555-555555555558'
retention_future_document_id='55555555-5555-5555-5555-555555555559'
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

http_code() {
  curl -sS -o /dev/null -w '%{http_code}' "$@"
}

cleanup() {
  stop_api
}
trap cleanup EXIT

rm -rf "$storage_root"
mkdir -p "$storage_root/recovery"

# The previous workflow step used the default Retention.Enabled=false configuration.
# Therefore all API-uploaded rows created there must still be non-expiring.
default_retention_rows=$(psql_cmd -At -c \
  "SELECT COUNT(*) FROM \"Documents\" WHERE \"CustomerId\" = '$customer_id' AND \"DeleteAt\" IS NOT NULL;")
test "$default_retention_rows" = '0'

# Scenario 8 in the main E2E deliberately leaves one other-tenant Uploaded fixture
# without a file. Remove it so this restart test has exactly the intended recovery candidates.
psql_cmd -c \
  "DELETE FROM \"Documents\" WHERE \"Id\" = '$other_fixture_document_id';"

# Start one healthy host with the explicitly enabled test retention policy.
start_api

processed_invoice_id=$(psql_cmd -At -c \
  "SELECT \"Id\" FROM \"Documents\" WHERE \"CustomerId\" = '$customer_id' AND \"OriginalFileName\" = 'supplier-invoice.pdf' AND \"Status\" = 'Processed' ORDER BY \"CreatedAt\" DESC LIMIT 1;")
test -n "$processed_invoice_id"

processed_attempts_before=$(curl -fsS \
  -H "X-DocFlow-Api-Key: $api_key" \
  "$base_url/api/documents/$processed_invoice_id/processing-diagnostics" \
  | jq -r '.processingAttempts')
test "$processed_attempts_before" = '1'

echo "Retention check: enabled policy stamps new uploads with future DeleteAt"
retention_upload_json=$(curl -fsS \
  -H "X-DocFlow-Api-Key: $api_key" \
  -X POST \
  -F 'File=@/tmp/supplier-invoice.pdf;type=application/pdf' \
  "$base_url/api/documents")
retention_upload_id=$(printf '%s' "$retention_upload_json" | jq -r '.id')
retention_delete_at=$(printf '%s' "$retention_upload_json" | jq -r '.deleteAt')
test -n "$retention_upload_id"
test "$retention_upload_id" != 'null'
test -n "$retention_delete_at"
test "$retention_delete_at" != 'null'
test "$(date -d "$retention_delete_at" +%s)" -gt "$(date +%s)"
wait_for_status "$retention_upload_id" 'Processed'

stop_api

cp /tmp/supplier-invoice.pdf "$storage_root/recovery/uploaded.pdf"
cp /tmp/supplier-invoice.pdf "$storage_root/recovery/processing.pdf"

psql_cmd -c \
  "DELETE FROM \"Documents\" WHERE \"Id\" IN ('$uploaded_document_id', '$processing_document_id');"

psql_cmd -c \
  "INSERT INTO \"Documents\" (\"Id\", \"CustomerId\", \"OriginalFileName\", \"ContentType\", \"StorageKey\", \"Size\", \"Status\", \"CreatedAt\") VALUES ('$uploaded_document_id', '$customer_id', '../restart-uploaded.pdf', 'application/pdf', 'recovery/uploaded.pdf', 1, 'Uploaded', NOW());"

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

echo "Scenario 10: original PDF access streams exact tenant-owned source bytes"

curl -fsS \
  -D /tmp/docflow-source-file.headers \
  -o /tmp/docflow-source-file.pdf \
  -H "X-DocFlow-Api-Key: $api_key" \
  "$base_url/api/documents/$uploaded_document_id/file"

cmp /tmp/supplier-invoice.pdf /tmp/docflow-source-file.pdf
grep -Eiq '^content-type: application/pdf' /tmp/docflow-source-file.headers
grep -Eiq '^content-disposition: attachment;.*filename="?restart-uploaded\.pdf"?' /tmp/docflow-source-file.headers

range_code=$(curl -sS \
  -o /tmp/docflow-source-range.bin \
  -w '%{http_code}' \
  -H "X-DocFlow-Api-Key: $api_key" \
  -H 'Range: bytes=0-4' \
  "$base_url/api/documents/$uploaded_document_id/file")
test "$range_code" = '206'
test "$(cat /tmp/docflow-source-range.bin)" = '%PDF-'

echo "Original PDF access base checks passed: bytes, headers, safe filename and range response verified."

echo "Scenario 11: terminal document deletion removes file and cascaded data"

uploaded_result_id=$(psql_cmd -At -c \
  "SELECT \"Id\" FROM \"ExtractionResults\" WHERE \"DocumentId\" = '$uploaded_document_id';")
test -n "$uploaded_result_id"

psql_cmd -c \
  "INSERT INTO \"DocumentReviews\" (\"Id\", \"DocumentId\", \"ExtractionResultId\", \"CorrectedDataJson\", \"Note\", \"ReviewedAt\") VALUES ('$review_id', '$uploaded_document_id', '$uploaded_result_id', '{\"verified\":true}'::jsonb, 'delete cascade fixture', NOW());"

test -f "$storage_root/recovery/uploaded.pdf"

# Active rows are inserted only after startup so the recovery service does not own them.
psql_cmd -c \
  "INSERT INTO \"Documents\" (\"Id\", \"CustomerId\", \"OriginalFileName\", \"ContentType\", \"StorageKey\", \"Size\", \"Status\", \"CreatedAt\") VALUES ('$uploaded_conflict_document_id', '$customer_id', 'delete-conflict-uploaded.pdf', 'application/pdf', 'recovery/conflict-uploaded.pdf', 1, 'Uploaded', NOW());"
psql_cmd -c \
  "INSERT INTO \"Documents\" (\"Id\", \"CustomerId\", \"OriginalFileName\", \"ContentType\", \"StorageKey\", \"Size\", \"Status\", \"CreatedAt\") VALUES ('$processing_conflict_document_id', '$customer_id', 'delete-conflict-processing.pdf', 'application/pdf', 'recovery/conflict-processing.pdf', 1, 'Processing', NOW());"
psql_cmd -c \
  "INSERT INTO \"Documents\" (\"Id\", \"CustomerId\", \"OriginalFileName\", \"ContentType\", \"StorageKey\", \"Size\", \"Status\", \"CreatedAt\") VALUES ('$failed_delete_document_id', '$customer_id', 'delete-failed.pdf', 'application/pdf', 'recovery/missing-failed.pdf', 1, 'Failed', NOW());"
psql_cmd -c \
  "INSERT INTO \"Documents\" (\"Id\", \"CustomerId\", \"OriginalFileName\", \"ContentType\", \"StorageKey\", \"Size\", \"Status\", \"CreatedAt\") VALUES ('$other_fixture_document_id', '$other_customer_id', 'delete-other-tenant.pdf', 'application/pdf', 'recovery/other-tenant.pdf', 1, 'Processed', NOW());"

cross_tenant_file_code=$(http_code \
  -H "X-DocFlow-Api-Key: $api_key" \
  "$base_url/api/documents/$other_fixture_document_id/file")
test "$cross_tenant_file_code" = '404'

missing_file_code=$(curl -sS \
  -o /tmp/docflow-missing-file.json \
  -w '%{http_code}' \
  -H "X-DocFlow-Api-Key: $api_key" \
  "$base_url/api/documents/$failed_delete_document_id/file")
test "$missing_file_code" = '500'
printf '%s' "$(cat /tmp/docflow-missing-file.json)" | jq -e '.title == "Source document file is unavailable."' >/dev/null
! grep -Fq "$storage_root" /tmp/docflow-missing-file.json
! grep -Fq 'recovery/missing-failed.pdf' /tmp/docflow-missing-file.json

cross_tenant_delete_code=$(http_code \
  -H "X-DocFlow-Api-Key: $api_key" \
  -X DELETE "$base_url/api/documents/$other_fixture_document_id")
test "$cross_tenant_delete_code" = '404'

uploaded_conflict_code=$(http_code \
  -H "X-DocFlow-Api-Key: $api_key" \
  -X DELETE "$base_url/api/documents/$uploaded_conflict_document_id")
test "$uploaded_conflict_code" = '409'

processing_conflict_code=$(http_code \
  -H "X-DocFlow-Api-Key: $api_key" \
  -X DELETE "$base_url/api/documents/$processing_conflict_document_id")
test "$processing_conflict_code" = '409'

active_rows=$(psql_cmd -At -c \
  "SELECT COUNT(*) FROM \"Documents\" WHERE \"Id\" IN ('$uploaded_conflict_document_id', '$processing_conflict_document_id');")
test "$active_rows" = '2'

delete_code=$(http_code \
  -H "X-DocFlow-Api-Key: $api_key" \
  -X DELETE "$base_url/api/documents/$uploaded_document_id")
test "$delete_code" = '204'

test ! -e "$storage_root/recovery/uploaded.pdf"

remaining_related_rows=$(psql_cmd -At -c \
  "SELECT (SELECT COUNT(*) FROM \"Documents\" WHERE \"Id\" = '$uploaded_document_id') + (SELECT COUNT(*) FROM \"ExtractionResults\" WHERE \"DocumentId\" = '$uploaded_document_id') + (SELECT COUNT(*) FROM \"DocumentReviews\" WHERE \"DocumentId\" = '$uploaded_document_id');")
test "$remaining_related_rows" = '0'

for deleted_path in \
  "/api/documents/$uploaded_document_id" \
  "/api/documents/$uploaded_document_id/file" \
  "/api/documents/$uploaded_document_id/processing-diagnostics" \
  "/api/documents/$uploaded_document_id/extraction-result" \
  "/api/documents/$uploaded_document_id/export?format=csv"; do
  deleted_code=$(http_code \
    -H "X-DocFlow-Api-Key: $api_key" \
    "$base_url$deleted_path")
  test "$deleted_code" = '404'
done

review_after_delete_code=$(http_code \
  -H "X-DocFlow-Api-Key: $api_key" \
  -H 'Content-Type: application/json' \
  -X PUT \
  -d '{}' \
  "$base_url/api/documents/$uploaded_document_id/review")
test "$review_after_delete_code" = '404'

repeat_delete_code=$(http_code \
  -H "X-DocFlow-Api-Key: $api_key" \
  -X DELETE "$base_url/api/documents/$uploaded_document_id")
test "$repeat_delete_code" = '404'

failed_delete_code=$(http_code \
  -H "X-DocFlow-Api-Key: $api_key" \
  -X DELETE "$base_url/api/documents/$failed_delete_document_id")
test "$failed_delete_code" = '204'

failed_remaining=$(psql_cmd -At -c \
  "SELECT COUNT(*) FROM \"Documents\" WHERE \"Id\" = '$failed_delete_document_id';")
test "$failed_remaining" = '0'

# Remove direct fixtures that intentionally remain after conflict/isolation checks.
psql_cmd -c \
  "DELETE FROM \"Documents\" WHERE \"Id\" IN ('$uploaded_conflict_document_id', '$processing_conflict_document_id', '$other_fixture_document_id');"

echo "Document deletion E2E passed: tenant isolation, active-state conflicts, terminal deletion, file cleanup and database cascades verified."

echo "Scenario 12: retention sweep removes only expired terminal documents"

cp /tmp/supplier-invoice.pdf "$storage_root/recovery/retention-expired.pdf"
cp /tmp/supplier-invoice.pdf "$storage_root/recovery/retention-active.pdf"
cp /tmp/supplier-invoice.pdf "$storage_root/recovery/retention-future.pdf"

psql_cmd -c \
  "INSERT INTO \"Documents\" (\"Id\", \"CustomerId\", \"OriginalFileName\", \"ContentType\", \"StorageKey\", \"Size\", \"Status\", \"CreatedAt\", \"DeleteAt\") VALUES ('$retention_expired_document_id', '$customer_id', 'retention-expired.pdf', 'application/pdf', 'recovery/retention-expired.pdf', 1, 'Processed', NOW(), NOW() - INTERVAL '1 minute');"
psql_cmd -c \
  "INSERT INTO \"Documents\" (\"Id\", \"CustomerId\", \"OriginalFileName\", \"ContentType\", \"StorageKey\", \"Size\", \"Status\", \"CreatedAt\", \"DeleteAt\") VALUES ('$retention_active_document_id', '$customer_id', 'retention-active.pdf', 'application/pdf', 'recovery/retention-active.pdf', 1, 'Uploaded', NOW(), NOW() - INTERVAL '1 minute');"
psql_cmd -c \
  "INSERT INTO \"Documents\" (\"Id\", \"CustomerId\", \"OriginalFileName\", \"ContentType\", \"StorageKey\", \"Size\", \"Status\", \"CreatedAt\", \"DeleteAt\") VALUES ('$retention_future_document_id', '$customer_id', 'retention-future.pdf', 'application/pdf', 'recovery/retention-future.pdf', 1, 'Processed', NOW(), NOW() + INTERVAL '1 day');"

expired_removed=false
for _ in $(seq 1 20); do
  expired_code=$(http_code \
    -H "X-DocFlow-Api-Key: $api_key" \
    "$base_url/api/documents/$retention_expired_document_id")

  if [ "$expired_code" = '404' ] && [ ! -e "$storage_root/recovery/retention-expired.pdf" ]; then
    expired_removed=true
    break
  fi

  sleep 1
done

test "$expired_removed" = 'true'

active_retention_code=$(http_code \
  -H "X-DocFlow-Api-Key: $api_key" \
  "$base_url/api/documents/$retention_active_document_id")
future_retention_code=$(http_code \
  -H "X-DocFlow-Api-Key: $api_key" \
  "$base_url/api/documents/$retention_future_document_id")

test "$active_retention_code" = '200'
test "$future_retention_code" = '200'
test -f "$storage_root/recovery/retention-active.pdf"
test -f "$storage_root/recovery/retention-future.pdf"

retention_remaining=$(psql_cmd -At -c \
  "SELECT COUNT(*) FROM \"Documents\" WHERE \"Id\" IN ('$retention_active_document_id', '$retention_future_document_id');")
test "$retention_remaining" = '2'

# Cleanup retention fixtures that are intentionally retained by policy.
psql_cmd -c \
  "DELETE FROM \"Documents\" WHERE \"Id\" IN ('$retention_active_document_id', '$retention_future_document_id');"
rm -f "$storage_root/recovery/retention-active.pdf" "$storage_root/recovery/retention-future.pdf"

echo "Retention E2E passed: default-off behavior, upload expiry stamping, expired terminal cleanup, active-state skip and future-expiry preservation verified."
