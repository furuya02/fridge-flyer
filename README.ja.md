# FridgeFlyer

[English](README.md)

Amazon Bedrock FlowsとClaudeの画像認識機能を使用して、小売店のチラシ画像から商品情報を自動抽出するサーバーレスアプリケーション。

## 概要

`FridgeFlyer`は、Amazon S3に保存されたチラシ画像を処理し、Amazon Bedrock Flowsを通じてClaude Opus 4.6の画像認識機能を使用して商品情報（商品名、単位、価格）を抽出します。抽出されたデータはJSONとして保存され、後続の処理に利用できます。

## 機能

- **AI画像分析**: Claude Opus 4.6（グローバル推論）による高精度な商品情報抽出
- **自動化ワークフロー**: Bedrock Flowsが処理パイプライン全体をオーケストレーション
- **包括的な抽出**: 商品名、単位、税込価格、税抜価格を抽出
- **Infrastructure as Code**: AWS CDK（TypeScript）でデプロイ
- **サーバーレスアーキテクチャ**: LambdaとBedrock Flowsによるスケーラブルな構成

## アーキテクチャ

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

## 前提条件

- 適切な認証情報で設定済みのAWS CLI
- Node.js 18.x以上
- AWS CDK CLI (`npm install -g aws-cdk`)
- AWSアカウントでBedrockのClaudeモデルアクセスが有効化済み

## インストール

```bash
git clone https://github.com/your-username/fridge-flyer.git
cd fridge-flyer/cdk
npm install
```

## デプロイ

```bash
cd cdk

# 初回のみ: CDKのブートストラップ
cdk bootstrap

# スタックをデプロイ
cdk deploy
```

## 使用方法

### 基本的な使用方法

1. チラシ画像をS3にアップロード:
```bash
aws s3 cp flyer.jpg s3://fridge-flyer-<your-account-id>/
```

2. AWSコンソールまたはCLIでBedrock Flowを実行

3. `results/`フォルダで結果を確認:
```bash
aws s3 ls s3://fridge-flyer-<your-account-id>/results/
```

### 出力形式

抽出されたデータはJSONとして保存されます:

```json
{
  "source_bucket": "fridge-flyer-123456789012",
  "source_key": "flyer.jpg",
  "description": "チラシから抽出された商品リスト...",
  "model_id": "global.anthropic.claude-opus-4-6-v1"
}
```

## 設定

`cdk/lib/fridge-flyer-stack.ts`を編集してカスタマイズ:

| パラメータ | 説明 | デフォルト値 |
|-----------|------|-------------|
| `SOURCE_KEY` | 入力画像ファイル名 | `flyer.jpg` |
| `MODEL_ID` | 使用するClaudeモデル | `global.anthropic.claude-opus-4-6-v1` |
| `bucketName` | S3バケット名パターン | `fridge-flyer-${ACCOUNT_ID}` |

## プロジェクト構成

```
fridge-flyer/
├── cdk/
│   ├── bin/cdk.ts                    # CDKアプリエントリポイント
│   ├── lib/fridge-flyer-stack.ts     # メインスタック定義
│   ├── lambda/
│   │   └── image-processor/
│   │       └── index.py              # 画像処理Lambda
│   ├── package.json
│   ├── tsconfig.json
│   └── cdk.json
├── README.md
├── README.ja.md
└── LICENSE
```

## 必要要件

- Python 3.12（Lambdaランタイム）
- Node.js 18.x以上
- AWS CDK 2.x
- Bedrockアクセスが有効なAWSアカウント

## ライセンス

MITライセンス - 詳細は[LICENSE](LICENSE)を参照してください。

## 著者

SIN

## コントリビューション

プルリクエストを歓迎します。大きな変更を行う場合は、まずIssueを作成して変更内容について議論してください。
