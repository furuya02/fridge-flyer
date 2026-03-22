"""
画像処理Lambda（Bedrock Flow Lambdaノード用）
S3から固定パスの画像を取得し、Bedrockで画像の説明を生成する
"""
import json
import os
import base64
import boto3
from typing import Any


def get_image_media_type(key: str) -> str:
    """
    ファイル拡張子からメディアタイプを取得する

    Args:
        key: S3オブジェクトキー

    Returns:
        メディアタイプ
    """
    key_lower = key.lower()
    if key_lower.endswith(".png"):
        return "image/png"
    elif key_lower.endswith(".gif"):
        return "image/gif"
    elif key_lower.endswith(".webp"):
        return "image/webp"
    else:
        return "image/jpeg"


def handler(event: dict[str, Any], context: Any) -> dict[str, Any]:
    """
    Bedrock Flowから呼び出され、S3から固定パスの画像を取得してLLMで説明を生成する

    Args:
        event: Bedrock Flowからの入力
        context: Lambdaコンテキスト

    Returns:
        画像の説明を含むレスポンス
    """
    print(f"Received event: {json.dumps(event)}")

    s3_client = boto3.client("s3")
    bedrock_runtime = boto3.client("bedrock-runtime")

    # 環境変数から固定パスを取得
    bucket = os.environ["SOURCE_BUCKET"]
    key = os.environ["SOURCE_KEY"]
    output_bucket = os.environ["OUTPUT_BUCKET"]
    model_id = os.environ.get("MODEL_ID", "global.anthropic.claude-opus-4-6-v1")

    print(f"Processing image: s3://{bucket}/{key}")

    # S3から画像を取得
    try:
        response = s3_client.get_object(Bucket=bucket, Key=key)
        image_data = response["Body"].read()
        media_type = get_image_media_type(key)
        print(f"Image loaded: {len(image_data)} bytes, media_type: {media_type}")
    except Exception as e:
        print(f"Error fetching image from S3: {str(e)}")
        return {
            "error": f"Failed to fetch image: {str(e)}",
            "bucket": bucket,
            "key": key
        }

    # Bedrockで画像の説明を生成
    try:
        response = bedrock_runtime.converse(
            modelId=model_id,
            messages=[
                {
                    "role": "user",
                    "content": [
                        {
                            "image": {
                                "format": media_type.split("/")[1],
                                "source": {
                                    "bytes": image_data
                                }
                            }
                        },
                        {
                            "text": """画像に映っている商品を【すべて漏れなく】一覧してください。省略せず、画像に見えるすべての商品を列挙してください。

各商品について以下の情報を記載：
1. 商品名
2. 単位（個、パックなど）
3. 価格（税込み）
4. 価格（税抜き）

※一部だけでなく、必ずすべての商品を出力してください。"""
                        }
                    ]
                }
            ]
        )

        description = ""
        for content_block in response.get("output", {}).get("message", {}).get("content", []):
            if "text" in content_block:
                description += content_block["text"]

        print(f"Generated description: {description[:200]}...")

        # 結果をS3に保存
        output_key = f"results/{key.rsplit('.', 1)[0]}_description.json"
        result = {
            "source_bucket": bucket,
            "source_key": key,
            "description": description,
            "model_id": model_id
        }

        s3_client.put_object(
            Bucket=output_bucket,
            Key=output_key,
            Body=json.dumps(result, ensure_ascii=False, indent=2),
            ContentType="application/json"
        )

        print(f"Result saved to s3://{output_bucket}/{output_key}")

        # Flow出力用に説明文を返す
        return description

    except Exception as e:
        print(f"Error calling Bedrock: {str(e)}")
        return f"Error: {str(e)}"
