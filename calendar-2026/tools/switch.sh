#!/usr/bin/env bash
# Kill switch, by hand with the owner's profile. Takes effect in seconds.
#   tools/switch.sh status | open | pause | close | off | disable
#   open    = mode open and functions back to their normal concurrency (api 5, processor 2)
#   pause   = mode paused: no API calls, pages and month photos keep working
#   close   = mode closed: one static "closed" page, zero origin traffic
#   off     = close, then concurrency 0 on api and processor (nothing can execute)
#   disable = last resort: disable the distribution itself (minutes to apply; stops request charges)
set -euo pipefail
ACTION="${1:-status}"
export AWS_PROFILE="${AWS_PROFILE:-personal}" AWS_REGION=us-east-1 AWS_PAGER=""
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
  disable)
    DIST="$(outputs DistributionId)"
    aws cloudfront get-distribution-config --id "$DIST" > /tmp/calendar-2026-dist.json
    ETAG="$(jq -r .ETag /tmp/calendar-2026-dist.json)"
    jq '.DistributionConfig | .Enabled = false' /tmp/calendar-2026-dist.json > /tmp/calendar-2026-dist-off.json
    aws cloudfront update-distribution --id "$DIST" --if-match "$ETAG" --distribution-config file:///tmp/calendar-2026-dist-off.json > /dev/null
    echo "distribution disabling (takes minutes); re-enable by deploying the stack again" ;;
  *) echo "usage: $0 status|open|pause|close|off|disable"; exit 64 ;;
esac
