# FridgeFlyer

[日本語](README.ja.md)

A serverless application that automatically extracts product information from retail flyer images using Amazon Bedrock Flows and Claude's vision capabilities.

## Overview

`FridgeFlyer` processes retail flyer images stored in Amazon S3 and extracts detailed product information (name, unit, price) using Claude Opus 4.6's image recognition through Amazon Bedrock Flows. The extracted data is saved as JSON for further processing.

## Features

- **AI-Powered Image Analysis**: Uses Claude Opus 4.6 (global inference) for accurate product extraction
- **Automated Workflow**: Bedrock Flows orchestrates the entire processing pipeline
- **Comprehensive Extraction**: Extracts product name, unit, tax-inclusive and tax-exclusive prices
- **Infrastructure as Code**: Deploy with AWS CDK (TypeScript)
- **Serverless Architecture**: Built on Lambda and Bedrock Flows for scalability

## Architecture

```
┌─────────────────────────────────────────────────────────────────────┐
│  S3 Bucket                                                          │
│  ├── flyer.jpg (supermarket flyer)                                  │
│  └── fridge.jpg (refrigerator contents)                             │
└─────────────────────────┬───────────────────────────────────────────┘
                          │
                          ▼
┌─────────────────────────────────────────────────────────────────────┐
│  Bedrock Flow                                                       │
│                                                                     │
│  ┌─────────┐    ┌─────────────────┐    ┌──────────────────┐        │
│  │  Input  │───►│ FlyerProcessor  │───►│                  │        │
│  │  Node   │    │    (Lambda)     │    │  RecipePrompt    │        │
│  │         │───►│ FridgeProcessor │───►│    (Claude)      │        │
│  └─────────┘    │    (Lambda)     │    │                  │        │
│                 └─────────────────┘    └────────┬─────────┘        │
│                                                 │                   │
│                 ┌───────────────────────────────┼───────────────┐  │
│                 │                               │               │  │
│                 ▼                               ▼               ▼  │
│  ┌──────────────────┐  ┌──────────────────┐  ┌──────────────────┐ │
│  │ ImageGenDish1    │  │ ImageGenDish2    │  │ ImageGenDessert  │ │
│  │    (Lambda)      │  │    (Lambda)      │  │    (Lambda)      │ │
│  └────────┬─────────┘  └────────┬─────────┘  └────────┬─────────┘ │
│           │                     │                     │            │
│           └─────────────────────┼─────────────────────┘            │
│                                 ▼                                   │
│                          ┌─────────────┐    ┌──────────┐           │
│                          │  MergeNode  │───►│  Output  │           │
│                          │  (Prompt)   │    │   Node   │           │
│                          └─────────────┘    └──────────┘           │
└─────────────────────────────────────────────────────────────────────┘
                                  │
                                  ▼
┌─────────────────────────────────────────────────────────────────────┐
│  S3 Bucket (results/)                                               │
│  ├── flyer_description.json                                         │
│  ├── fridge_description.json                                        │
│  ├── recipe_dish1.png                                               │
│  ├── recipe_dish2.png                                               │
│  └── recipe_dessert.png                                             │
└─────────────────────────────────────────────────────────────────────┘
```

## Prerequisites

- AWS CLI configured with appropriate credentials
- Node.js 18.x or later
- AWS CDK CLI (`npm install -g aws-cdk`)
- Bedrock model access enabled for Claude in your AWS account

## Installation

```bash
git clone https://github.com/your-username/fridge-flyer.git
cd fridge-flyer/cdk
npm install
```

## Deployment

```bash
cd cdk

# First time only: Bootstrap CDK
cdk bootstrap

# Deploy the stack
cdk deploy
```

### Updating Flow Version (After Redeployment)

After redeploying CDK, you need to create a new Flow version and update the Alias:

```bash
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
```

## Usage

### Basic Usage

1. Upload images to S3:
```bash
aws s3 cp flyer.jpg s3://fridge-flyer-<your-account-id>/
aws s3 cp fridge.jpg s3://fridge-flyer-<your-account-id>/
```

2. Get Flow ID and Alias ID:
```bash
aws cloudformation describe-stacks \
  --stack-name FridgeFlyerStack \
  --query "Stacks[0].Outputs" \
  --output table
```

3. Invoke the Bedrock Flow via CLI:
```bash
FLOW_ID="<FlowId from output>"
ALIAS_ID="<FlowAliasId from output>"

aws bedrock-agent-runtime invoke-flow \
  --region ap-northeast-1 \
  --flow-identifier "$FLOW_ID" \
  --flow-alias-identifier "$ALIAS_ID" \
  --inputs '[{"content":{"document":"start"},"nodeName":"FlowInputNode","nodeOutputName":"document"}]'
```

4. Check the results in the `results/` folder:
```bash
aws s3 ls s3://fridge-flyer-<your-account-id>/results/
```

### Output Files

| File | Description |
|------|-------------|
| `results/flyer_description.json` | Product list extracted from supermarket flyer |
| `results/fridge_description.json` | Contents list extracted from refrigerator |
| `results/recipe_dish1.png` | Generated image for Dish 1 |
| `results/recipe_dish2.png` | Generated image for Dish 2 |
| `results/recipe_dessert.png` | Generated image for Dessert |

### Output Format

The extracted data is saved as JSON:

```json
{
  "source_bucket": "fridge-flyer-123456789012",
  "source_key": "flyer.jpg",
  "description": "Product list extracted from the flyer...",
  "model_id": "global.anthropic.claude-opus-4-6-v1"
}
```

## Configuration

Edit `cdk/lib/fridge-flyer-stack.ts` to customize:

| Parameter | Description | Default |
|-----------|-------------|---------|
| `SOURCE_KEY` | Input image filename | `flyer.jpg` |
| `MODEL_ID` | Claude model to use | `global.anthropic.claude-opus-4-6-v1` |
| `bucketName` | S3 bucket name pattern | `fridge-flyer-${ACCOUNT_ID}` |

## Project Structure

```
fridge-flyer/
├── cdk/
│   ├── bin/cdk.ts                    # CDK app entry point
│   ├── lib/fridge-flyer-stack.ts     # Main stack definition
│   ├── lambda/
│   │   ├── image-processor/
│   │   │   └── index.py              # Image analysis Lambda (Claude)
│   │   └── image-generator/
│   │       └── index.py              # Recipe image generation Lambda (Nova Canvas)
│   ├── package.json
│   ├── tsconfig.json
│   └── cdk.json
├── README.md
├── README.ja.md
└── LICENSE
```

## Requirements

- Python 3.12 (Lambda runtime)
- Node.js 18.x+
- AWS CDK 2.x
- AWS Account with Bedrock access

## License

MIT License - see [LICENSE](LICENSE) for details.

## Author

SIN

## Contributing

Pull requests are welcome. For major changes, please open an issue first to discuss what you would like to change.
