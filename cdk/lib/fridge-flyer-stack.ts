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

    // 画像処理Lambda用のIAMロール
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

    // 画像処理Lambda（Flowノード用）
    const imageProcessorLambda = new lambda.Function(this, 'ImageProcessorLambda', {
      functionName: 'fridge-flyer-image-processor',
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

    // Bedrock Flow用のIAMロール
    const flowRole = new iam.Role(this, 'BedrockFlowRole', {
      assumedBy: new iam.ServicePrincipal('bedrock.amazonaws.com'),
    });

    // FlowからLambdaを呼び出す権限
    flowRole.addToPolicy(new iam.PolicyStatement({
      actions: ['lambda:InvokeFunction'],
      resources: [imageProcessorLambda.functionArn],
    }));

    // FlowからBedrockモデルを呼び出す権限
    flowRole.addToPolicy(new iam.PolicyStatement({
      actions: ['bedrock:InvokeModel'],
      resources: ['*'],
    }));

    // Bedrock Flow定義
    const flow = new bedrock.CfnFlow(this, 'FridgeFlyerFlow', {
      name: 'fridge-flyer-flow',
      executionRoleArn: flowRole.roleArn,
      definition: {
        nodes: [
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
          {
            name: 'ImageProcessorNode',
            type: 'LambdaFunction',
            configuration: {
              lambdaFunction: {
                lambdaArn: imageProcessorLambda.functionArn,
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
          {
            name: 'InputToProcessor',
            source: 'FlowInputNode',
            target: 'ImageProcessorNode',
            type: 'Data',
            configuration: {
              data: {
                sourceOutput: 'document',
                targetInput: 'codeHookInput',
              },
            },
          },
          {
            name: 'ProcessorToOutput',
            source: 'ImageProcessorNode',
            target: 'FlowOutputNode',
            type: 'Data',
            configuration: {
              data: {
                sourceOutput: 'functionResponse',
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

    new cdk.CfnOutput(this, 'ImageProcessorLambdaArn', {
      value: imageProcessorLambda.functionArn,
      description: 'Image Processor Lambda ARN',
    });
  }
}
