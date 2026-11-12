#!/usr/bin/env bash
# Kill switch, by hand with the owner's profile. Takes effect in seconds.
#   tools/switch.sh status | open | pause | close | off | disable | enable
# The same actions are available as the GitHub workflow "Calendar 2026 switch".
#   open    = mode open and functions back to their normal concurrency (api 5, processor 2)
#   pause   = mode paused: no API calls, pages and month photos keep working
#   close   = mode closed: one static "closed" page, zero origin traffic
#   off     = close, then concurrency 0 on api and processor (nothing can execute)
#   disable = last resort: turn the distribution itself off (minutes to apply; stops request charges)
#   enable  = turn the distribution back on (minutes), then run "open"
set -euo pipefail
ACTION="${1:-status}"
if [ -z "${GITHUB_ACTIONS:-}" ]; then export AWS_PROFILE="${AWS_PROFILE:-personal}"; fi
export AWS_REGION=us-east-1 AWS_PAGER=""
STACK=calendar-2026
outputs() { aws cloudformation describe-stacks --stack-name $STACK --query "Stacks[0].Outputs[?OutputKey=='$1'].OutputValue" --output text; }
KVS_ARN="$(outputs KeyValueStoreArn)"

mode_set() {
  local etag; etag="$(aws cloudfront-keyvaluestore describe-key-value-store --kvs-arn "$KVS_ARN" --query ETag --output text)"
  aws cloudfront-keyvaluestore put-key --kvs-arn "$KVS_ARN" --key mode --value "$1" --if-match "$etag" > /dev/null
  echo "mode=$1"
}
concurrency() {
  aws lambda put-function-concurrency --function-name calendar-2026-api --reserved-concurrent-executions "$1" > /dev/null
  aws lambda put-function-concurrency --function-name calendar-2026-processor --reserved-concurrent-executions "$2" > /dev/null
  echo "concurrency api=$1 processor=$2"
}

distribution() {
  local dist cfg etag
  dist="$(outputs DistributionId)"
  cfg="$(aws cloudfront get-distribution-config --id "$dist")"
  etag="$(jq -r .ETag <<<"$cfg")"
  jq --argjson on "$1" '.DistributionConfig | .Enabled = $on' <<<"$cfg" > "${TMPDIR:-/tmp}/calendar-2026-dist.json"
  aws cloudfront update-distribution --id "$dist" --if-match "$etag" --distribution-config "file://${TMPDIR:-/tmp}/calendar-2026-dist.json" > /dev/null
  echo "distribution enabled=$1 (takes a few minutes to apply at every edge)"
}

case "$ACTION" in
  status)
    echo "mode=$(aws cloudfront-keyvaluestore get-key --kvs-arn "$KVS_ARN" --key mode --query Value --output text 2>/dev/null || echo '(unset)')"
    for f in calendar-2026-api calendar-2026-processor; do
      echo "$f concurrency=$(aws lambda get-function-concurrency --function-name $f --query ReservedConcurrentExecutions --output text)"
    done
    echo "distribution enabled=$(aws cloudfront get-distribution --id "$(outputs DistributionId)" --query Distribution.DistributionConfig.Enabled --output text)" ;;
  open)  concurrency 5 2; mode_set open ;;
  pause) mode_set paused ;;
  close) mode_set closed ;;
  off)   mode_set closed; concurrency 0 0 ;;
  disable) distribution false ;;
  enable)  distribution true ;;
  *) echo "usage: $0 status|open|pause|close|off|disable|enable"; exit 64 ;;
esac
