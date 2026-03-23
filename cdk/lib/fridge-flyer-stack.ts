import * as cdk from 'aws-cdk-lib/core';
import * as s3 from 'aws-cdk-lib/aws-s3';
import * as lambda from 'aws-cdk-lib/aws-lambda';
import * as iam from 'aws-cdk-lib/aws-iam';
import * as bedrock from 'aws-cdk-lib/aws-bedrock';
import { Construct } from 'constructs';

export class FridgeFlyerStack extends cdk.Stack {
  constructor(scope: Construct, id: string, props?: cdk.StackProps) {
    super(scope, id, props);

    // S3バケットを新規作成
    const bucket = new s3.Bucket(this, 'FridgeFlyerBucket', {
      bucketName: `fridge-flyer-${cdk.Aws.ACCOUNT_ID}`,
      removalPolicy: cdk.RemovalPolicy.DESTROY,
      autoDeleteObjects: true,
    });

    // 画像処理Lambda用のIAMロール（共通）
    const imageProcessorRole = new iam.Role(this, 'ImageProcessorRole', {
      assumedBy: new iam.ServicePrincipal('lambda.amazonaws.com'),
      managedPolicies: [
        iam.ManagedPolicy.fromAwsManagedPolicyName('service-role/AWSLambdaBasicExecutionRole'),
      ],
    });

    // S3アクセス権限
    imageProcessorRole.addToPolicy(new iam.PolicyStatement({
      actions: ['s3:GetObject', 's3:PutObject'],
      resources: [bucket.bucketArn, `${bucket.bucketArn}/*`],
    }));

    // Bedrockアクセス権限
    imageProcessorRole.addToPolicy(new iam.PolicyStatement({
      actions: ['bedrock:InvokeModel', 'bedrock:Converse'],
      resources: ['*'],
    }));

    // チラシ処理Lambda（flyer.jpg用）
    const flyerProcessorLambda = new lambda.Function(this, 'FlyerProcessorLambda', {
      functionName: 'fridge-flyer-flyer-processor',
      runtime: lambda.Runtime.PYTHON_3_12,
      handler: 'index.handler',
      code: lambda.Code.fromAsset('lambda/image-processor'),
      role: imageProcessorRole,
      timeout: cdk.Duration.minutes(5),
      memorySize: 1024,
      environment: {
        SOURCE_BUCKET: bucket.bucketName,
        SOURCE_KEY: 'flyer.jpg',
        OUTPUT_BUCKET: bucket.bucketName,
        MODEL_ID: 'global.anthropic.claude-opus-4-6-v1',
      },
    });

    // 冷蔵庫処理Lambda（fridge.jpg用）
    const fridgeProcessorLambda = new lambda.Function(this, 'FridgeProcessorLambda', {
      functionName: 'fridge-flyer-fridge-processor',
      runtime: lambda.Runtime.PYTHON_3_12,
      handler: 'index.handler',
      code: lambda.Code.fromAsset('lambda/image-processor'),
      role: imageProcessorRole,
      timeout: cdk.Duration.minutes(5),
      memorySize: 1024,
      environment: {
        SOURCE_BUCKET: bucket.bucketName,
        SOURCE_KEY: 'fridge.jpg',
        OUTPUT_BUCKET: bucket.bucketName,
        MODEL_ID: 'global.anthropic.claude-opus-4-6-v1',
      },
    });

    // 画像生成Lambda用のIAMロール
    const imageGeneratorRole = new iam.Role(this, 'ImageGeneratorRole', {
      assumedBy: new iam.ServicePrincipal('lambda.amazonaws.com'),
      managedPolicies: [
        iam.ManagedPolicy.fromAwsManagedPolicyName('service-role/AWSLambdaBasicExecutionRole'),
      ],
    });

    // S3書き込み権限
    imageGeneratorRole.addToPolicy(new iam.PolicyStatement({
      actions: ['s3:PutObject'],
      resources: [`${bucket.bucketArn}/*`],
    }));

    // Bedrock画像生成権限
    imageGeneratorRole.addToPolicy(new iam.PolicyStatement({
      actions: ['bedrock:InvokeModel'],
      resources: ['*'],
    }));

    // 画像生成Lambda（料理1用）
    const imageGenDish1Lambda = new lambda.Function(this, 'ImageGenDish1Lambda', {
      functionName: 'fridge-flyer-image-gen-dish1',
      runtime: lambda.Runtime.PYTHON_3_12,
      handler: 'index.handler',
      code: lambda.Code.fromAsset('lambda/image-generator'),
      role: imageGeneratorRole,
      timeout: cdk.Duration.minutes(5),
      memorySize: 1024,
      environment: {
        OUTPUT_BUCKET: bucket.bucketName,
        RECIPE_INDEX: '1',
        IMAGE_MODEL_ID: 'amazon.nova-canvas-v1:0',
      },
    });

    // 画像生成Lambda（料理2用）
    const imageGenDish2Lambda = new lambda.Function(this, 'ImageGenDish2Lambda', {
      functionName: 'fridge-flyer-image-gen-dish2',
      runtime: lambda.Runtime.PYTHON_3_12,
      handler: 'index.handler',
      code: lambda.Code.fromAsset('lambda/image-generator'),
      role: imageGeneratorRole,
      timeout: cdk.Duration.minutes(5),
      memorySize: 1024,
      environment: {
        OUTPUT_BUCKET: bucket.bucketName,
        RECIPE_INDEX: '2',
        IMAGE_MODEL_ID: 'amazon.nova-canvas-v1:0',
      },
    });

    // 画像生成Lambda（デザート用）
    const imageGenDessertLambda = new lambda.Function(this, 'ImageGenDessertLambda', {
      functionName: 'fridge-flyer-image-gen-dessert',
      runtime: lambda.Runtime.PYTHON_3_12,
      handler: 'index.handler',
      code: lambda.Code.fromAsset('lambda/image-generator'),
      role: imageGeneratorRole,
      timeout: cdk.Duration.minutes(5),
      memorySize: 1024,
      environment: {
        OUTPUT_BUCKET: bucket.bucketName,
        RECIPE_INDEX: '3',
        IMAGE_MODEL_ID: 'amazon.nova-canvas-v1:0',
      },
    });

    // Bedrock Flow用のIAMロール
    const flowRole = new iam.Role(this, 'BedrockFlowRole', {
      assumedBy: new iam.ServicePrincipal('bedrock.amazonaws.com'),
    });

    // FlowからLambdaを呼び出す権限
    flowRole.addToPolicy(new iam.PolicyStatement({
      actions: ['lambda:InvokeFunction'],
      resources: [
        flyerProcessorLambda.functionArn,
        fridgeProcessorLambda.functionArn,
        imageGenDish1Lambda.functionArn,
        imageGenDish2Lambda.functionArn,
        imageGenDessertLambda.functionArn,
      ],
    }));

    // FlowからBedrockモデルを呼び出す権限
    flowRole.addToPolicy(new iam.PolicyStatement({
      actions: ['bedrock:InvokeModel'],
      resources: ['*'],
    }));

    // レシピ生成用プロンプトテンプレート
    const recipePromptTemplate = `あなたは料理の専門家です。以下の情報をもとに、レシピを3種類提案してください。

## 冷蔵庫の中身
{{fridge_contents}}

## スーパーのチラシ（特売品）
{{flyer_contents}}

## 条件
- 冷蔵庫にある食材を中心に使用してください
- チラシの特売品から1〜3品買い足せば作れるレシピを提案してください
- 料理2品とデザート1品を提案してください
- 買い足す食材は必ずチラシに掲載されている商品から選び、チラシに記載の価格を使用してください

## 出力形式（この形式を厳守してください）

### 料理1: [料理名]
**紹介**: [この料理の簡単な紹介（1〜2文）]
**材料**:
- [材料1] … [分量]
- [材料2] … [分量]
**レシピ**:
1. [手順1]
2. [手順2]
**買い物リスト**:
- [商品名] … [税抜価格]円

### 料理2: [料理名]
**紹介**: [この料理の簡単な紹介（1〜2文）]
**材料**:
- [材料1] … [分量]
- [材料2] … [分量]
**レシピ**:
1. [手順1]
2. [手順2]
**買い物リスト**:
- [商品名] … [税抜価格]円

### デザート: [デザート名]
**紹介**: [このデザートの簡単な紹介（1〜2文）]
**材料**:
- [材料1] … [分量]
- [材料2] … [分量]
**レシピ**:
1. [手順1]
2. [手順2]
**買い物リスト**:
- [商品名] … [税抜価格]円

---

## お買い物まとめ

| 買い足し品 | 価格（税抜） | 使用するレシピ |
|---|---|---|
| [商品名1] | [価格]円 | [料理名] |
| [商品名2] | [価格]円 | [料理名] |
| [商品名3] | [価格]円 | [料理名] |
| **合計** | **[合計金額]円** | |

冷蔵庫の食材を活かしつつ、約[合計金額]円の買い足しで3品が揃います。`;

    // Bedrock Flow定義
    // Input → [FlyerLambda, FridgeLambda] → Prompt → [ImageGen1, ImageGen2, ImageGen3] → Output
    const flow = new bedrock.CfnFlow(this, 'FridgeFlyerFlow', {
      name: 'fridge-flyer-flow',
      executionRoleArn: flowRole.roleArn,
      definition: {
        nodes: [
          // 入力ノード
          {
            name: 'FlowInputNode',
            type: 'Input',
            configuration: {
              input: {},
            },
            outputs: [
              {
                name: 'document',
                type: 'String',
              },
            ],
          },
          // チラシ処理ノード
          {
            name: 'FlyerProcessorNode',
            type: 'LambdaFunction',
            configuration: {
              lambdaFunction: {
                lambdaArn: flyerProcessorLambda.functionArn,
              },
            },
            inputs: [
              {
                name: 'codeHookInput',
                type: 'String',
                expression: '$.data',
              },
            ],
            outputs: [
              {
                name: 'functionResponse',
                type: 'String',
              },
            ],
          },
          // 冷蔵庫処理ノード
          {
            name: 'FridgeProcessorNode',
            type: 'LambdaFunction',
            configuration: {
              lambdaFunction: {
                lambdaArn: fridgeProcessorLambda.functionArn,
              },
            },
            inputs: [
              {
                name: 'codeHookInput',
                type: 'String',
                expression: '$.data',
              },
            ],
            outputs: [
              {
                name: 'functionResponse',
                type: 'String',
              },
            ],
          },
          // レシピ生成プロンプトノード
          {
            name: 'RecipePromptNode',
            type: 'Prompt',
            configuration: {
              prompt: {
                sourceConfiguration: {
                  inline: {
                    modelId: 'global.anthropic.claude-opus-4-6-v1',
                    templateType: 'TEXT',
                    inferenceConfiguration: {
                      text: {
                        maxTokens: 4096,
                        temperature: 0.9,
                      },
                    },
                    templateConfiguration: {
                      text: {
                        text: recipePromptTemplate,
                        inputVariables: [
                          { name: 'fridge_contents' },
                          { name: 'flyer_contents' },
                        ],
                      },
                    },
                  },
                },
              },
            },
            inputs: [
              {
                name: 'fridge_contents',
                type: 'String',
                expression: '$.data',
              },
              {
                name: 'flyer_contents',
                type: 'String',
                expression: '$.data',
              },
            ],
            outputs: [
              {
                name: 'modelCompletion',
                type: 'String',
              },
            ],
          },
          // 画像生成ノード（料理1）
          {
            name: 'ImageGenDish1Node',
            type: 'LambdaFunction',
            configuration: {
              lambdaFunction: {
                lambdaArn: imageGenDish1Lambda.functionArn,
              },
            },
            inputs: [
              {
                name: 'codeHookInput',
                type: 'String',
                expression: '$.data',
              },
            ],
            outputs: [
              {
                name: 'functionResponse',
                type: 'String',
              },
            ],
          },
          // 画像生成ノード（料理2）
          {
            name: 'ImageGenDish2Node',
            type: 'LambdaFunction',
            configuration: {
              lambdaFunction: {
                lambdaArn: imageGenDish2Lambda.functionArn,
              },
            },
            inputs: [
              {
                name: 'codeHookInput',
                type: 'String',
                expression: '$.data',
              },
            ],
            outputs: [
              {
                name: 'functionResponse',
                type: 'String',
              },
            ],
          },
          // 画像生成ノード（デザート）
          {
            name: 'ImageGenDessertNode',
            type: 'LambdaFunction',
            configuration: {
              lambdaFunction: {
                lambdaArn: imageGenDessertLambda.functionArn,
              },
            },
            inputs: [
              {
                name: 'codeHookInput',
                type: 'String',
                expression: '$.data',
              },
            ],
            outputs: [
              {
                name: 'functionResponse',
                type: 'String',
              },
            ],
          },
          // マージノード（Promptで入力を待ち合わせてレシピテキストのみ出力）
          // 高速なHaikuモデルを使用（待機目的のため）
          {
            name: 'MergeNode',
            type: 'Prompt',
            configuration: {
              prompt: {
                sourceConfiguration: {
                  inline: {
                    modelId: 'anthropic.claude-3-haiku-20240307-v1:0',
                    templateType: 'TEXT',
                    inferenceConfiguration: {
                      text: {
                        maxTokens: 4096,
                        temperature: 0,
                      },
                    },
                    templateConfiguration: {
                      text: {
                        text: '以下のテキストをそのまま出力してください。変更や追加は一切しないでください。\n\n{{recipe_text}}',
                        inputVariables: [
                          { name: 'recipe_text' },
                          { name: 'image1_path' },
                          { name: 'image2_path' },
                          { name: 'image3_path' },
                        ],
                      },
                    },
                  },
                },
              },
            },
            inputs: [
              {
                name: 'recipe_text',
                type: 'String',
                expression: '$.data',
              },
              {
                name: 'image1_path',
                type: 'String',
                expression: '$.data',
              },
              {
                name: 'image2_path',
                type: 'String',
                expression: '$.data',
              },
              {
                name: 'image3_path',
                type: 'String',
                expression: '$.data',
              },
            ],
            outputs: [
              {
                name: 'modelCompletion',
                type: 'String',
              },
            ],
          },
          // 出力ノード
          {
            name: 'FlowOutputNode',
            type: 'Output',
            configuration: {
              output: {},
            },
            inputs: [
              {
                name: 'document',
                type: 'String',
                expression: '$.data',
              },
            ],
          },
        ],
        connections: [
          // Input → FlyerProcessor
          {
            name: 'InputToFlyerProcessor',
            source: 'FlowInputNode',
            target: 'FlyerProcessorNode',
            type: 'Data',
            configuration: {
              data: {
                sourceOutput: 'document',
                targetInput: 'codeHookInput',
              },
            },
          },
          // Input → FridgeProcessor
          {
            name: 'InputToFridgeProcessor',
            source: 'FlowInputNode',
            target: 'FridgeProcessorNode',
            type: 'Data',
            configuration: {
              data: {
                sourceOutput: 'document',
                targetInput: 'codeHookInput',
              },
            },
          },
          // FlyerProcessor → RecipePrompt (flyer_contents)
          {
            name: 'FlyerToPrompt',
            source: 'FlyerProcessorNode',
            target: 'RecipePromptNode',
            type: 'Data',
            configuration: {
              data: {
                sourceOutput: 'functionResponse',
                targetInput: 'flyer_contents',
              },
            },
          },
          // FridgeProcessor → RecipePrompt (fridge_contents)
          {
            name: 'FridgeToPrompt',
            source: 'FridgeProcessorNode',
            target: 'RecipePromptNode',
            type: 'Data',
            configuration: {
              data: {
                sourceOutput: 'functionResponse',
                targetInput: 'fridge_contents',
              },
            },
          },
          // RecipePrompt → MergeNode (recipe_text)
          {
            name: 'PromptToMerge',
            source: 'RecipePromptNode',
            target: 'MergeNode',
            type: 'Data',
            configuration: {
              data: {
                sourceOutput: 'modelCompletion',
                targetInput: 'recipe_text',
              },
            },
          },
          // RecipePrompt → ImageGenDish1
          {
            name: 'PromptToImageGen1',
            source: 'RecipePromptNode',
            target: 'ImageGenDish1Node',
            type: 'Data',
            configuration: {
              data: {
                sourceOutput: 'modelCompletion',
                targetInput: 'codeHookInput',
              },
            },
          },
          // RecipePrompt → ImageGenDish2
          {
            name: 'PromptToImageGen2',
            source: 'RecipePromptNode',
            target: 'ImageGenDish2Node',
            type: 'Data',
            configuration: {
              data: {
                sourceOutput: 'modelCompletion',
                targetInput: 'codeHookInput',
              },
            },
          },
          // RecipePrompt → ImageGenDessert
          {
            name: 'PromptToImageGen3',
            source: 'RecipePromptNode',
            target: 'ImageGenDessertNode',
            type: 'Data',
            configuration: {
              data: {
                sourceOutput: 'modelCompletion',
                targetInput: 'codeHookInput',
              },
            },
          },
          // ImageGenDish1 → MergeNode (image1_path)
          {
            name: 'ImageGen1ToMerge',
            source: 'ImageGenDish1Node',
            target: 'MergeNode',
            type: 'Data',
            configuration: {
              data: {
                sourceOutput: 'functionResponse',
                targetInput: 'image1_path',
              },
            },
          },
          // ImageGenDish2 → MergeNode (image2_path)
          {
            name: 'ImageGen2ToMerge',
            source: 'ImageGenDish2Node',
            target: 'MergeNode',
            type: 'Data',
            configuration: {
              data: {
                sourceOutput: 'functionResponse',
                targetInput: 'image2_path',
              },
            },
          },
          // ImageGenDessert → MergeNode (image3_path)
          {
            name: 'ImageGen3ToMerge',
            source: 'ImageGenDessertNode',
            target: 'MergeNode',
            type: 'Data',
            configuration: {
              data: {
                sourceOutput: 'functionResponse',
                targetInput: 'image3_path',
              },
            },
          },
          // MergeNode → FlowOutput
          {
            name: 'MergeToOutput',
            source: 'MergeNode',
            target: 'FlowOutputNode',
            type: 'Data',
            configuration: {
              data: {
                sourceOutput: 'modelCompletion',
                targetInput: 'document',
              },
            },
          },
        ],
      },
    });

    // Flow Version（公開バージョンを作成）
    const flowVersion = new bedrock.CfnFlowVersion(this, 'FridgeFlyerFlowVersion', {
      flowArn: flow.attrArn,
    });

    // Flow Alias
    const flowAlias = new bedrock.CfnFlowAlias(this, 'FridgeFlyerFlowAlias', {
      flowArn: flow.attrArn,
      name: 'live',
      routingConfiguration: [
        {
          flowVersion: flowVersion.attrVersion,
        },
      ],
    });

    // 出力
    new cdk.CfnOutput(this, 'BucketName', {
      value: bucket.bucketName,
      description: 'S3 Bucket Name',
    });

    new cdk.CfnOutput(this, 'FlowId', {
      value: flow.attrId,
      description: 'Bedrock Flow ID',
    });

    new cdk.CfnOutput(this, 'FlowArn', {
      value: flow.attrArn,
      description: 'Bedrock Flow ARN',
    });

    new cdk.CfnOutput(this, 'FlowAliasId', {
      value: flowAlias.attrId,
      description: 'Bedrock Flow Alias ID',
    });

    new cdk.CfnOutput(this, 'FlyerProcessorLambdaArn', {
      value: flyerProcessorLambda.functionArn,
      description: 'Flyer Processor Lambda ARN',
    });

    new cdk.CfnOutput(this, 'FridgeProcessorLambdaArn', {
      value: fridgeProcessorLambda.functionArn,
      description: 'Fridge Processor Lambda ARN',
    });

    new cdk.CfnOutput(this, 'ImageGenDish1LambdaArn', {
      value: imageGenDish1Lambda.functionArn,
      description: 'Image Generator Dish1 Lambda ARN',
    });

    new cdk.CfnOutput(this, 'ImageGenDish2LambdaArn', {
      value: imageGenDish2Lambda.functionArn,
      description: 'Image Generator Dish2 Lambda ARN',
    });

    new cdk.CfnOutput(this, 'ImageGenDessertLambdaArn', {
      value: imageGenDessertLambda.functionArn,
      description: 'Image Generator Dessert Lambda ARN',
    });
  }
}
