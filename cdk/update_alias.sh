# Get Flow ID
FLOW_ID=$(aws cloudformation describe-stacks \
  --stack-name FridgeFlyerStack \
  --query "Stacks[0].Outputs[?OutputKey=='FlowId'].OutputValue" \
  --output text)

ALIAS_ID=$(aws cloudformation describe-stacks \
  --stack-name FridgeFlyerStack \
  --query "Stacks[0].Outputs[?OutputKey=='FlowAliasId'].OutputValue" \
  --output text)

# Create new version
VERSION=$(aws bedrock-agent create-flow-version \
  --flow-identifier "$FLOW_ID" \
  --query "version" \
  --output text)

# Update Alias to new version
aws bedrock-agent update-flow-alias \
  --flow-identifier "$FLOW_ID" \
  --alias-identifier "$ALIAS_ID" \
  --name live \
  --routing-configuration "[{\"flowVersion\":\"$VERSION\"}]"

echo "Flow updated to version $VERSION"