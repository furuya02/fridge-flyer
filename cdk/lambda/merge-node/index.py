"""
マージノードLambda（Bedrock Flow Lambdaノード用）
複数の入力を待機し、レシピテキストをそのまま返す
LLMを使用せずに並列処理の同期を実現する
"""
import json
from typing import Any


def handler(event: dict[str, Any], context: Any) -> str:
    """
    Bedrock Flowから呼び出され、複数の入力を受け取りレシピテキストを返す

    このLambdaは、3つの画像生成Lambdaとレシピ生成の完了を待機するために使用される。
    Bedrock Flowでは、すべての入力が到着するまでノードの実行が待機されるため、
    この単純なLambdaで並列処理の同期が実現できる。

    Bedrock Flow Lambdaノードの入力形式:
    {
        "node": {
            "name": "MergeNode",
            "inputs": [
                {"name": "recipe_text", "value": "...", "type": "STRING"},
                {"name": "image1_path", "value": "...", "type": "STRING"},
                ...
            ]
        },
        "flow": {...},
        "messageVersion": "1.0"
    }

    Args:
        event: Bedrock Flowからの入力
        context: Lambdaコンテキスト

    Returns:
        レシピテキスト（そのまま返す）
    """
    print(f"Received event: {json.dumps(event)}")

    recipe_text = ""

    # Bedrock Flowからの入力形式に対応
    if isinstance(event, dict) and "node" in event:
        # Bedrock Flow Lambda nodeの入力形式
        node_inputs = event.get("node", {}).get("inputs", [])

        # inputsリストから各値を取得
        inputs_dict: dict[str, str] = {}
        for input_item in node_inputs:
            name = input_item.get("name", "")
            value = input_item.get("value", "")
            inputs_dict[name] = value

        recipe_text = inputs_dict.get("recipe_text", "")
        image1_path = inputs_dict.get("image1_path", "")
        image2_path = inputs_dict.get("image2_path", "")
        image3_path = inputs_dict.get("image3_path", "")

        print(f"recipe_text length: {len(str(recipe_text))}")
        print(f"image1_path: {image1_path}")
        print(f"image2_path: {image2_path}")
        print(f"image3_path: {image3_path}")

    elif isinstance(event, dict):
        # フォールバック: 直接キーとして渡される場合
        recipe_text = event.get("recipe_text", "")
        if not recipe_text and "codeHookInput" in event:
            recipe_text = event.get("codeHookInput", "")
        print(f"Fallback mode - recipe_text length: {len(str(recipe_text))}")

    else:
        # 文字列として渡された場合
        recipe_text = str(event)
        print(f"Event was string, length: {len(recipe_text)}")

    # レシピテキストをそのまま返す
    return str(recipe_text)
