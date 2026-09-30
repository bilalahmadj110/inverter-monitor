#!/usr/bin/env bash
# Deploy or update the relay stack, then upload the Lambda code straight from a zip
# (no deployment bucket). Idempotent; re-run after any change under aws/ or static/.
#
#   AWS_PROFILE=nursepal AWS_REGION=ap-south-1 PYTHON=python3 aws/deploy.sh
set -euo pipefail
cd "$(dirname "$0")/.."

PROFILE="${AWS_PROFILE:-nursepal}"
REGION="${AWS_REGION:-ap-south-1}"
STACK="${STACK_NAME:-inverter-relay}"
PY="${PYTHON:-python3}"
SHA="$(git rev-parse --short HEAD 2>/dev/null || echo dev)"
AWS=(aws --profile "$PROFILE" --region "$REGION")

echo "==> pre-rendering pages"
"$PY" aws/build_pages.py

echo "==> packaging Lambda"
mkdir -p build
rm -f build/relay.zip
(cd aws/lambda && zip -qr ../../build/relay.zip handler.py pages static -x '*.DS_Store')
ls -la build/relay.zip

echo "==> deploying stack $STACK in $REGION (profile $PROFILE)"
"${AWS[@]}" cloudformation deploy \
  --stack-name "$STACK" \
  --template-file aws/template.yaml \
  --capabilities CAPABILITY_NAMED_IAM \
  --no-fail-on-empty-changeset \
  --parameter-overrides AppVersion="$SHA" \
  --tags project=inverter-monitor

FN="$("${AWS[@]}" cloudformation describe-stacks --stack-name "$STACK" \
      --query "Stacks[0].Outputs[?OutputKey=='FunctionName'].OutputValue" --output text)"

echo "==> uploading code to $FN"
"${AWS[@]}" lambda update-function-code --function-name "$FN" --zip-file fileb://build/relay.zip \
  --query 'CodeSha256' --output text
"${AWS[@]}" lambda wait function-updated --function-name "$FN"

echo "==> outputs"
"${AWS[@]}" cloudformation describe-stacks --stack-name "$STACK" \
  --query 'Stacks[0].Outputs[].[OutputKey,OutputValue]' --output table
