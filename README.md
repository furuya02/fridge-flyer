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
┌──────────────────┐
│   S3 Bucket      │
│   (flyer.jpg)    │
└────────┬─────────┘
         │
         ▼
┌──────────────────┐
│  Bedrock Flow    │
│                  │
│ ┌──────────────┐ │
│ │ Input Node   │ │
│ └──────┬───────┘ │
│        ▼         │
│ ┌──────────────┐ │
│ │ Lambda Node  │─┼──► ImageProcessorLambda
│ └──────┬───────┘ │         │
│        ▼         │         ▼
│ ┌──────────────┐ │   Claude Opus 4.6
│ │ Output Node  │ │         │
│ └──────────────┘ │         ▼
└──────────────────┘   S3 results/*.json
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

## Usage

### Basic Usage

1. Upload a flyer image to S3:
```bash
aws s3 cp flyer.jpg s3://fridge-flyer-<your-account-id>/
```

2. Invoke the Bedrock Flow via AWS Console or CLI

3. Check the results in the `results/` folder:
```bash
aws s3 ls s3://fridge-flyer-<your-account-id>/results/
```

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
│   │   └── image-processor/
│   │       └── index.py              # Image processing Lambda
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
