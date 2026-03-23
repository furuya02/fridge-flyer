"""
レシピ画像生成Lambda（Bedrock Flow Lambdaノード用）
レシピテキストから指定されたレシピを抽出し、画像を生成してS3に保存する
"""
import json
import os
import re
import base64
import boto3
from typing import Any


def extract_recipe_by_index(recipe_text: str, recipe_index: int) -> dict[str, str]:
    """
    レシピテキストから指定されたインデックスのレシピを抽出する

    Args:
        recipe_text: 全レシピテキスト（マークダウン形式）
        recipe_index: 抽出するレシピのインデックス（1, 2, 3）

    Returns:
        レシピ情報（name, description）
    """
    # レシピセクションを正規表現で抽出
    # ### 料理1: [料理名] または ### デザート: [デザート名]
    patterns = {
        1: r"### 料理1[::]\s*(.+?)(?:\n\*\*紹介\*\*[::]\s*(.+?))?(?=\n\*\*材料\*\*|\n###|\Z)",
        2: r"### 料理2[::]\s*(.+?)(?:\n\*\*紹介\*\*[::]\s*(.+?))?(?=\n\*\*材料\*\*|\n###|\Z)",
        3: r"### デザート[::]\s*(.+?)(?:\n\*\*紹介\*\*[::]\s*(.+?))?(?=\n\*\*材料\*\*|\n###|\Z)",
    }

    pattern = patterns.get(recipe_index)
    if not pattern:
        return {"name": f"Recipe {recipe_index}", "description": "A delicious dish"}

    match = re.search(pattern, recipe_text, re.DOTALL)
    if match:
        name = match.group(1).strip()
        description = match.group(2).strip() if match.group(2) else name
        return {"name": name, "description": description}

    return {"name": f"Recipe {recipe_index}", "description": "A delicious dish"}


def generate_image_prompt(recipe_name: str, recipe_description: str) -> str:
    """
    画像生成用のプロンプトを作成する（Nova Canvas上限1024文字）

    Args:
        recipe_name: レシピ名
        recipe_description: レシピの説明

    Returns:
        画像生成プロンプト（最大900文字）
    """
    # レシピ名を短く（最大50文字）
    short_name = recipe_name[:50] if len(recipe_name) > 50 else recipe_name

    prompt = f"Professional food photography of {short_name}, beautifully plated, soft natural lighting, top-down angle, restaurant quality, appetizing"

    # 900文字以内に収める
    return prompt[:900]


def handler(event: dict[str, Any], context: Any) -> str:
    """
    Bedrock Flowから呼び出され、レシピの画像を生成してS3に保存する

    Args:
        event: Bedrock Flowからの入力（レシピテキスト）
        context: Lambdaコンテキスト

    Returns:
        生成された画像のS3 URI
    """
    print(f"Received event: {json.dumps(event)}")

    s3_client = boto3.client("s3")
    bedrock_runtime = boto3.client("bedrock-runtime")

    # 環境変数から設定を取得
    output_bucket = os.environ["OUTPUT_BUCKET"]
    recipe_index = int(os.environ.get("RECIPE_INDEX", "1"))
    image_model_id = os.environ.get("IMAGE_MODEL_ID", "amazon.nova-canvas-v1:0")

    # Bedrock Flowからの入力を取得
    # Lambda nodeへの入力はcodeHookInputとして渡される
    recipe_text = event
    if isinstance(event, dict):
        recipe_text = event.get("codeHookInput", event.get("inputText", str(event)))

    print(f"Processing recipe index: {recipe_index}")
    print(f"Recipe text length: {len(str(recipe_text))}")

    # レシピを抽出
    recipe_info = extract_recipe_by_index(str(recipe_text), recipe_index)
    recipe_name = recipe_info["name"]
    recipe_description = recipe_info["description"]

    print(f"Extracted recipe: {recipe_name}")

    # 画像生成プロンプトを作成
    image_prompt = generate_image_prompt(recipe_name, recipe_description)
    print(f"Image prompt: {image_prompt[:200]}...")

    # 出力ファイル名を決定
    recipe_type = "dessert" if recipe_index == 3 else f"dish{recipe_index}"
    output_key = f"results/recipe_{recipe_type}.png"

    try:
        # Nova Canvasで画像生成
        response = bedrock_runtime.invoke_model(
            modelId=image_model_id,
            body=json.dumps({
                "taskType": "TEXT_IMAGE",
                "textToImageParams": {
                    "text": image_prompt,
                },
                "imageGenerationConfig": {
                    "numberOfImages": 1,
                    "height": 1024,
                    "width": 1024,
                    "quality": "standard",
                    "seed": 0,
                }
            }),
            contentType="application/json",
            accept="application/json"
        )

        response_body = json.loads(response["body"].read())
        image_data = base64.b64decode(response_body["images"][0])

        print(f"Image generated: {len(image_data)} bytes")

        # S3に画像を保存
        s3_client.put_object(
            Bucket=output_bucket,
            Key=output_key,
            Body=image_data,
            ContentType="image/png"
        )

        result_uri = f"s3://{output_bucket}/{output_key}"
        print(f"Image saved to {result_uri}")

        return result_uri

    except Exception as e:
        print(f"Error generating image: {str(e)}")
        return f"Error: {str(e)}"
