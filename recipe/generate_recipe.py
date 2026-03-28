#!/usr/bin/env python3
"""
レシピ生成スクリプト
冷蔵庫・チラシ画像をアップロードし、Bedrock Flowでレシピを生成し、HTMLを出力する
"""
import json
import os
import re
import webbrowser
import io
import boto3
from botocore.config import Config
from pathlib import Path
from typing import Any
from PIL import Image

# 定数
FLOW_ID = "9MM6CG8EW8"
FLOW_ALIAS_ID = "V6I8GK1NE8"
BUCKET_NAME = "fridge-flyer-439028474478"
REGION = "ap-northeast-1"

# パス設定
SCRIPT_DIR = Path(__file__).parent
FLYER_PATH = SCRIPT_DIR / "flyer.jpg"
FRIDGE_PATH = SCRIPT_DIR / "fridge.jpg"
RESULTS_DIR = SCRIPT_DIR / "results"
OUTPUT_DIR = SCRIPT_DIR / "output"


def compress_image_if_needed(image_path: Path, max_size_mb: float = 3.5) -> bytes:
    """
    画像が指定サイズを超える場合は圧縮する

    Bedrockの制限は5MBだが、Base64エンコードで約1.37倍になるため、
    3.5MB以下に圧縮する（3.5 * 1.37 ≈ 4.8MB）

    Args:
        image_path: 画像ファイルのパス
        max_size_mb: 最大サイズ（MB）

    Returns:
        圧縮後の画像データ（bytes）
    """
    max_size_bytes = int(max_size_mb * 1024 * 1024)

    # 元のファイルサイズを確認
    original_size = image_path.stat().st_size

    if original_size <= max_size_bytes:
        # 圧縮不要
        return image_path.read_bytes()

    print(f"    (画像を圧縮中: {original_size / 1024 / 1024:.2f}MB -> ", end="")

    # Pillowで画像を開く
    with Image.open(image_path) as img:
        # RGBに変換（PNGなどのRGBA対応）
        if img.mode in ("RGBA", "P"):
            img = img.convert("RGB")

        # 段階的に圧縮を試行
        quality = 85
        max_dimension = 2000

        while quality >= 30:
            # リサイズ
            if max(img.size) > max_dimension:
                ratio = max_dimension / max(img.size)
                new_size = (int(img.size[0] * ratio), int(img.size[1] * ratio))
                resized_img = img.resize(new_size, Image.Resampling.LANCZOS)
            else:
                resized_img = img

            # JPEG圧縮
            buffer = io.BytesIO()
            resized_img.save(buffer, format="JPEG", quality=quality, optimize=True)
            compressed_data = buffer.getvalue()

            if len(compressed_data) <= max_size_bytes:
                print(f"{len(compressed_data) / 1024 / 1024:.2f}MB)")
                return compressed_data

            # さらに圧縮を試行
            quality -= 10
            max_dimension -= 200

        # 最終手段：最低品質で圧縮
        buffer = io.BytesIO()
        ratio = 1000 / max(img.size)
        new_size = (int(img.size[0] * ratio), int(img.size[1] * ratio))
        resized_img = img.resize(new_size, Image.Resampling.LANCZOS)
        resized_img.save(buffer, format="JPEG", quality=30, optimize=True)
        compressed_data = buffer.getvalue()
        print(f"{len(compressed_data) / 1024 / 1024:.2f}MB)")
        return compressed_data


def upload_images_to_s3(s3_client: Any) -> None:
    """画像をS3にアップロードする（必要に応じて圧縮）"""
    print("画像をS3にアップロード中...")

    # flyer.jpg
    if FLYER_PATH.exists():
        image_data = compress_image_if_needed(FLYER_PATH)
        s3_client.put_object(
            Bucket=BUCKET_NAME,
            Key="flyer.jpg",
            Body=image_data,
            ContentType="image/jpeg"
        )
        print(f"  - {FLYER_PATH.name} -> s3://{BUCKET_NAME}/flyer.jpg")
    else:
        print(f"  - 警告: {FLYER_PATH} が見つかりません")

    # fridge.jpg
    if FRIDGE_PATH.exists():
        image_data = compress_image_if_needed(FRIDGE_PATH)
        s3_client.put_object(
            Bucket=BUCKET_NAME,
            Key="fridge.jpg",
            Body=image_data,
            ContentType="image/jpeg"
        )
        print(f"  - {FRIDGE_PATH.name} -> s3://{BUCKET_NAME}/fridge.jpg")
    else:
        print(f"  - 警告: {FRIDGE_PATH} が見つかりません")


def invoke_bedrock_flow(bedrock_agent_runtime: Any) -> str:
    """Bedrock Flowを実行し、レスポンスを取得する"""
    print("Bedrock Flowを実行中...")
    print("  （画像分析とレシピ生成に数分かかります。お待ちください...）")

    response = bedrock_agent_runtime.invoke_flow(
        flowIdentifier=FLOW_ID,
        flowAliasIdentifier=FLOW_ALIAS_ID,
        inputs=[
            {
                "content": {"document": "start"},
                "nodeName": "FlowInputNode",
                "nodeOutputName": "document",
            }
        ],
    )

    # ストリーミングレスポンスを処理
    result_text = ""
    event_count = 0
    for event in response.get("responseStream", []):
        event_count += 1
        if event_count % 10 == 0:
            print(f"  - 処理中... ({event_count} イベント受信)")

        if "flowOutputEvent" in event:
            content = event["flowOutputEvent"].get("content", {})
            if "document" in content:
                result_text = content["document"]
                print("  - 出力を受信しました")
        elif "flowCompletionEvent" in event:
            print("  - Flow完了")

    print(f"  - レスポンス取得完了（{len(result_text)}文字）")
    return result_text


def save_result_md(result_text: str) -> None:
    """結果をresults/result.mdに保存する"""
    RESULTS_DIR.mkdir(parents=True, exist_ok=True)
    result_path = RESULTS_DIR / "result.md"
    result_path.write_text(result_text, encoding="utf-8")
    print(f"  - 結果を保存: {result_path}")


def download_results_from_s3(s3_client: Any) -> None:
    """S3のresults/からファイルをダウンロードする"""
    print("S3から結果ファイルをダウンロード中...")
    RESULTS_DIR.mkdir(parents=True, exist_ok=True)

    # results/内のオブジェクトをリスト
    response = s3_client.list_objects_v2(Bucket=BUCKET_NAME, Prefix="results/")

    for obj in response.get("Contents", []):
        key = obj["Key"]
        if key == "results/":
            continue

        filename = key.replace("results/", "")
        local_path = RESULTS_DIR / filename

        s3_client.download_file(BUCKET_NAME, key, str(local_path))
        print(f"  - {key} -> {local_path}")


def parse_recipe_markdown(md_text: str) -> dict[str, Any]:
    """マークダウンテキストからレシピ情報を抽出する"""
    recipes = []

    # 料理1, 料理2, デザートを抽出
    patterns = [
        (r"### 料理1[::]\s*(.+?)\n", "料理 1", False),
        (r"### 料理2[::]\s*(.+?)\n", "料理 2", False),
        (r"### デザート[::]\s*(.+?)\n", "デザート", True),
    ]

    for i, (pattern, label, is_dessert) in enumerate(patterns):
        match = re.search(pattern, md_text)
        if match:
            name = match.group(1).strip()

            # 紹介文を抽出
            desc_pattern = rf"### (?:料理{i+1}|デザート)[::].+?\n\*\*紹介\*\*[::]\s*(.+?)(?=\n\*\*材料\*\*|\n###|\Z)"
            desc_match = re.search(desc_pattern, md_text, re.DOTALL)
            description = desc_match.group(1).strip() if desc_match else ""

            # 材料を抽出
            ingredients = []
            ing_section = re.search(
                rf"### (?:料理{i+1}|デザート)[::].+?\*\*材料\*\*[::]\s*\n((?:- .+\n)+)",
                md_text,
                re.DOTALL,
            )
            if ing_section:
                for line in ing_section.group(1).strip().split("\n"):
                    if line.startswith("- "):
                        ingredients.append(line[2:].strip())

            # レシピ手順を抽出
            steps = []
            steps_section = re.search(
                rf"### (?:料理{i+1}|デザート)[::].+?\*\*レシピ\*\*[::]\s*\n((?:\d+\. .+\n?)+)",
                md_text,
                re.DOTALL,
            )
            if steps_section:
                for line in steps_section.group(1).strip().split("\n"):
                    step_match = re.match(r"\d+\.\s*(.+)", line)
                    if step_match:
                        steps.append(step_match.group(1).strip())

            # 買い物リストを抽出
            shopping = []
            shop_section = re.search(
                rf"### (?:料理{i+1}|デザート)[::].+?\*\*買い物リスト\*\*[::]\s*\n((?:- .+\n?)+)",
                md_text,
                re.DOTALL,
            )
            if shop_section:
                for line in shop_section.group(1).strip().split("\n"):
                    if line.startswith("- "):
                        shopping.append(line[2:].strip())

            recipes.append(
                {
                    "label": label,
                    "name": name,
                    "description": description,
                    "ingredients": ingredients,
                    "steps": steps,
                    "shopping": shopping,
                    "is_dessert": is_dessert,
                    "image": f"recipe_{'dessert' if is_dessert else f'dish{i+1}'}.png",
                }
            )

    # お買い物まとめセクションを抽出
    shopping_summary: dict[str, Any] = {"items": [], "total": "", "note": ""}

    # 形式1: テーブル形式の買い物リストを抽出（「お買い物まとめ」または「買い物まとめ」に対応）
    # 2列または3列のテーブルに対応
    table_match = re.search(
        r"## .*買い物まとめ.*\n\n\|.+\|\n\|[-\s|]+\|\n((?:\|.+\|\n)+)",
        md_text,
        re.DOTALL,
    )
    if table_match:
        for line in table_match.group(1).strip().split("\n"):
            cols = [c.strip() for c in line.split("|") if c.strip()]
            if len(cols) >= 2:
                item_name = cols[0].replace("**", "")
                price = cols[1].replace("**", "")
                # 3列目がある場合はレシピ名として取得
                recipe_name = cols[2].replace("**", "") if len(cols) >= 3 else ""
                if "合計" in item_name.lower():
                    shopping_summary["total"] = price
                else:
                    item_data: dict[str, str] = {"name": item_name, "price": price}
                    if recipe_name:
                        item_data["recipe"] = recipe_name
                    shopping_summary["items"].append(item_data)
    else:
        # 形式2: 各レシピの買い物リストから抽出
        # **買い物リスト**: の後に続く行を抽出
        for i, (pattern, label, is_dessert) in enumerate(patterns):
            shop_pattern = rf"### (?:料理{i+1}|デザート)[::].+?\*\*買い物リスト\*\*[：:]?\s*\n((?:- .+\n?)+)"
            shop_section = re.search(shop_pattern, md_text, re.DOTALL)
            if shop_section:
                for line in shop_section.group(1).strip().split("\n"):
                    if line.startswith("- "):
                        item_text = line[2:].strip()
                        # 価格を抽出（例: "サニーレタス（イオン特売 128円／税抜）"）
                        price_match = re.search(r"(\d[\d,]*円)", item_text)
                        if price_match:
                            price = price_match.group(1)
                            # 商品名を整形
                            name = re.sub(r"[（(].*?[）)]", "", item_text).strip()
                            name = re.sub(r"\*\*", "", name)
                            # 重複チェック
                            if not any(item["name"] == name for item in shopping_summary["items"]):
                                shopping_summary["items"].append({"name": name, "price": price})

        # 形式2: **買い物合計（税抜）: ...** を抽出
        total_match = re.search(r"\*\*買い物合計[（(]税抜[）)][：:]\s*(.+?)\*\*", md_text)
        if total_match:
            shopping_summary["total"] = total_match.group(1).strip()

    # 注記を抽出（「> ※」または「> 💡」形式に対応）
    note_match = re.search(r"> [※💡].*?\*\*(.+?)\*\*[：:]\s*(.+?)(?=\n\n|\Z)", md_text, re.DOTALL)
    if note_match:
        shopping_summary["note"] = note_match.group(2).strip()

    # 最後のメッセージを抽出（様々な形式に対応）
    final_msg_match = re.search(
        r"\n\n(冷蔵庫の食材を.+?(?:仕上がります|ください)[！!]?)",
        md_text,
        re.DOTALL
    )
    if final_msg_match:
        shopping_summary["final_message"] = final_msg_match.group(1).strip()

    return {"recipes": recipes, "shopping_summary": shopping_summary}


def load_description_json(filename: str) -> str:
    """results/のJSONファイルからdescriptionフィールドを読み込む"""
    json_path = RESULTS_DIR / filename
    if json_path.exists():
        try:
            data = json.loads(json_path.read_text(encoding="utf-8"))
            return data.get("description", "")
        except (json.JSONDecodeError, KeyError):
            return ""
    return ""


def generate_html(recipe_data: dict[str, Any]) -> str:
    """レシピデータからHTMLを生成する"""
    recipes = recipe_data.get("recipes", [])
    shopping_summary = recipe_data.get("shopping_summary", {})

    # JSONからdescriptionを読み込み、JavaScriptエスケープ
    fridge_description = load_description_json("fridge_description.json")
    flyer_description = load_description_json("flyer_description.json")

    # JavaScriptの文字列リテラル用にエスケープ
    fridge_desc_escaped = fridge_description.replace("\\", "\\\\").replace("`", "\\`").replace("$", "\\$")
    flyer_desc_escaped = flyer_description.replace("\\", "\\\\").replace("`", "\\`").replace("$", "\\$")

    # レシピカードのHTML生成
    recipe_cards = []
    for recipe in recipes:
        # 材料リスト
        ingredients_html = ""
        for ing in recipe.get("ingredients", []):
            ingredients_html += f'                  <li>{ing}</li>\n'

        # 買い物リスト（緑色タグ）
        for item in recipe.get("shopping", []):
            ingredients_html += f'                  <li class="buy">{item}</li>\n'

        # レシピ手順
        steps_html = ""
        for step in recipe.get("steps", []):
            steps_html += f"                  <li>{step}</li>\n"

        # ラベルクラス
        label_class = "recipe-label dessert" if recipe.get("is_dessert") else "recipe-label"

        card = f"""          <!-- {recipe.get('label')} -->
          <div class="recipe-card">
            <img
              src="../results/{recipe.get('image')}"
              alt="{recipe.get('name')}"
            />
            <div class="recipe-body">
              <span class="{label_class}">{recipe.get('label')}</span>
              <h3>{recipe.get('name')}</h3>
              <p class="recipe-desc">
                {recipe.get('description')}
              </p>
              <div class="ingredients">
                <h4>材料</h4>
                <ul>
{ingredients_html.rstrip()}
                </ul>
              </div>
              <details>
                <summary>作り方を見る</summary>
                <ol class="steps">
{steps_html.rstrip()}
                </ol>
              </details>
            </div>
          </div>
"""
        recipe_cards.append(card)

    recipe_section = "\n".join(recipe_cards)

    # お買い物まとめセクションの生成
    shopping_html = ""
    if shopping_summary.get("items") or shopping_summary.get("total"):
        # 3列目（使用するレシピ）があるかチェック
        has_recipe_col = any(item.get("recipe") for item in shopping_summary.get("items", []))

        items_rows = ""
        for item in shopping_summary.get("items", []):
            if has_recipe_col:
                items_rows += f"""              <tr>
                <td>{item.get('name', '')}</td>
                <td>{item.get('price', '')}</td>
                <td>{item.get('recipe', '')}</td>
              </tr>
"""
            else:
                items_rows += f"""              <tr>
                <td>{item.get('name', '')}</td>
                <td>{item.get('price', '')}</td>
              </tr>
"""

        total_html = ""
        if shopping_summary.get("total"):
            total_html = f'<p class="total">買い足し合計: {shopping_summary.get("total")}</p>'

        note_html = ""
        if shopping_summary.get("note"):
            note_html = f'<p class="note">※{shopping_summary.get("note")}</p>'

        final_msg = ""
        if shopping_summary.get("final_message"):
            msg = shopping_summary.get("final_message", "").replace("**", "").replace("\n", "")
            final_msg = f'<p class="note" style="margin-top: 12px;">{msg}</p>'

        # テーブルヘッダー（3列または2列）
        if has_recipe_col:
            table_header = """            <thead>
              <tr>
                <th>買い足し品</th>
                <th>価格（税抜）</th>
                <th>使用するレシピ</th>
              </tr>
            </thead>"""
        else:
            table_header = """            <thead>
              <tr>
                <th>買い足し品</th>
                <th>価格（税抜）</th>
              </tr>
            </thead>"""

        shopping_html = f"""
      <!-- お買い物まとめ -->
      <section>
        <h2 class="section-title">お買い物まとめ</h2>
        <div class="shopping-summary">
          <h3>チラシから買い足す商品</h3>
          <table>
{table_header}
            <tbody>
{items_rows.rstrip()}
            </tbody>
          </table>
          {total_html}
          {note_html}
          {final_msg}
        </div>
      </section>
"""

    # HTMLテンプレート
    html = f'''<!DOCTYPE html>
<html lang="ja">
  <head>
    <meta charset="UTF-8" />
    <meta name="viewport" content="width=device-width, initial-scale=1.0" />
    <title>Fridge Flyer - 冷蔵庫×チラシ レシピ提案</title>
    <style>
      :root {{
        --primary: #e85d3a;
        --primary-light: #fff5f2;
        --accent: #2d8a4e;
        --accent-light: #e8f5e9;
        --text: #333;
        --text-light: #666;
        --bg: #fafafa;
        --card-bg: #fff;
        --border: #e0e0e0;
        --shadow: 0 2px 12px rgba(0, 0, 0, 0.08);
      }}

      * {{
        margin: 0;
        padding: 0;
        box-sizing: border-box;
      }}

      body {{
        font-family: "Hiragino Kaku Gothic ProN", "Noto Sans JP", sans-serif;
        background: var(--bg);
        color: var(--text);
        line-height: 1.7;
      }}

      .container {{
        max-width: 960px;
        margin: 0 auto;
        padding: 0 20px;
      }}

      header {{
        background: linear-gradient(135deg, var(--primary), #d04a2a);
        color: #fff;
        padding: 40px 0;
        text-align: center;
      }}

      header h1 {{
        font-size: 2rem;
        margin-bottom: 8px;
        letter-spacing: 0.05em;
      }}

      header p {{
        font-size: 1rem;
        opacity: 0.9;
      }}

      section {{
        margin: 40px 0;
      }}

      .section-title {{
        font-size: 1.4rem;
        border-left: 4px solid var(--primary);
        padding-left: 12px;
        margin-bottom: 24px;
        color: var(--text);
      }}

      .source-grid {{
        display: grid;
        grid-template-columns: 1fr 1fr;
        gap: 24px;
      }}

      .source-card {{
        background: var(--card-bg);
        border-radius: 12px;
        box-shadow: var(--shadow);
        overflow: hidden;
      }}

      .source-card img {{
        width: 100%;
        height: 240px;
        object-fit: cover;
        cursor: zoom-in;
      }}

      .source-card .card-body {{
        padding: 16px 20px;
        cursor: pointer;
        transition: background 0.2s;
      }}

      .source-card .card-body:hover {{
        background: var(--primary-light);
      }}

      .source-card h3 {{
        font-size: 1.1rem;
        margin-bottom: 8px;
        color: var(--primary);
      }}

      .source-card p {{
        font-size: 0.85rem;
        color: var(--text-light);
      }}

      .recipe-list {{
        display: flex;
        flex-direction: column;
        gap: 32px;
      }}

      .recipe-card {{
        background: var(--card-bg);
        border-radius: 12px;
        box-shadow: var(--shadow);
        overflow: hidden;
        display: grid;
        grid-template-columns: 320px 1fr;
        align-items: start;
      }}

      .recipe-card img {{
        width: 100%;
        height: 280px;
        object-fit: cover;
      }}

      .recipe-card .recipe-body {{
        padding: 24px 28px;
        display: flex;
        flex-direction: column;
        gap: 10px;
      }}

      .recipe-card .recipe-label {{
        display: inline-block;
        background: var(--primary);
        color: #fff;
        font-size: 0.75rem;
        padding: 3px 10px;
        border-radius: 20px;
        width: fit-content;
      }}

      .recipe-card .recipe-label.dessert {{
        background: var(--accent);
      }}

      .recipe-card h3 {{
        font-size: 1.25rem;
      }}

      .recipe-card .recipe-desc {{
        font-size: 0.9rem;
        color: var(--text-light);
      }}

      .recipe-card .ingredients {{
        margin-top: 4px;
      }}

      .recipe-card .ingredients h4 {{
        font-size: 0.85rem;
        color: var(--primary);
        margin-bottom: 4px;
      }}

      .recipe-card .ingredients ul {{
        list-style: none;
        display: flex;
        flex-wrap: wrap;
        gap: 6px;
      }}

      .recipe-card .ingredients li {{
        background: var(--primary-light);
        font-size: 0.8rem;
        padding: 3px 10px;
        border-radius: 16px;
        color: var(--primary);
      }}

      .recipe-card .ingredients li.buy {{
        background: var(--accent-light);
        color: var(--accent);
      }}

      .recipe-card details {{
        margin-top: 4px;
      }}

      .recipe-card summary {{
        font-size: 0.85rem;
        font-weight: bold;
        color: var(--primary);
        cursor: pointer;
        user-select: none;
      }}

      .recipe-card .steps {{
        margin-top: 8px;
        padding-left: 20px;
        font-size: 0.85rem;
        color: var(--text-light);
      }}

      .recipe-card .steps li {{
        background: none;
        color: var(--text-light);
        padding: 2px 0;
        border-radius: 0;
        font-size: 0.85rem;
        display: list-item;
        list-style: decimal;
      }}

      .tag-legend {{
        display: flex;
        gap: 16px;
        margin-bottom: 16px;
        font-size: 0.8rem;
        color: var(--text-light);
      }}

      .tag-legend span {{
        display: inline-flex;
        align-items: center;
        gap: 4px;
      }}

      .tag-legend .dot {{
        display: inline-block;
        width: 10px;
        height: 10px;
        border-radius: 50%;
      }}

      .tag-legend .dot.fridge {{
        background: var(--primary-light);
        border: 1px solid var(--primary);
      }}

      .tag-legend .dot.flyer {{
        background: var(--accent-light);
        border: 1px solid var(--accent);
      }}

      .modal-overlay {{
        display: none;
        position: fixed;
        top: 0;
        left: 0;
        width: 100%;
        height: 100%;
        background: rgba(0, 0, 0, 0.8);
        z-index: 1000;
        justify-content: center;
        align-items: center;
        cursor: zoom-out;
      }}

      .modal-overlay.active {{
        display: flex;
      }}

      .modal-overlay img {{
        max-width: 90%;
        max-height: 90%;
        object-fit: contain;
        border-radius: 8px;
        box-shadow: 0 4px 30px rgba(0, 0, 0, 0.5);
      }}

      .text-modal-overlay {{
        display: none;
        position: fixed;
        top: 0;
        left: 0;
        width: 100%;
        height: 100%;
        background: rgba(0, 0, 0, 0.7);
        z-index: 1001;
        justify-content: center;
        align-items: center;
      }}

      .text-modal-overlay.active {{
        display: flex;
      }}

      .text-modal-content {{
        background: #fff;
        border-radius: 12px;
        max-width: 800px;
        max-height: 80vh;
        width: 90%;
        padding: 24px;
        overflow-y: auto;
        position: relative;
        box-shadow: 0 4px 30px rgba(0, 0, 0, 0.3);
      }}

      .text-modal-content .close-btn {{
        position: absolute;
        top: 12px;
        right: 16px;
        font-size: 1.5rem;
        cursor: pointer;
        color: var(--text-light);
      }}

      .text-modal-content .close-btn:hover {{
        color: var(--text);
      }}

      .text-modal-content h1 {{
        font-size: 1.4rem;
        color: var(--primary);
        margin-bottom: 16px;
      }}

      .text-modal-content h2 {{
        font-size: 1.1rem;
        color: var(--text);
        margin: 16px 0 8px;
        border-bottom: 1px solid var(--border);
        padding-bottom: 4px;
      }}

      .text-modal-content h3 {{
        font-size: 1rem;
        color: var(--text);
        margin: 12px 0 8px;
      }}

      .text-modal-content table {{
        width: 100%;
        border-collapse: collapse;
        margin: 12px 0;
        font-size: 0.85rem;
      }}

      .text-modal-content th {{
        text-align: left;
        padding: 8px 10px;
        background: var(--primary-light);
        color: var(--primary);
        font-weight: bold;
      }}

      .text-modal-content td {{
        padding: 8px 10px;
        border-bottom: 1px solid var(--border);
      }}

      .text-modal-content p {{
        margin: 8px 0;
        line-height: 1.6;
        font-size: 0.9rem;
      }}

      .text-modal-content hr {{
        border: none;
        border-top: 1px solid var(--border);
        margin: 16px 0;
      }}

      .shopping-summary {{
        background: var(--card-bg);
        border-radius: 12px;
        box-shadow: var(--shadow);
        padding: 24px 28px;
        margin-top: 24px;
      }}

      .shopping-summary h3 {{
        font-size: 1.1rem;
        color: var(--accent);
        margin-bottom: 16px;
      }}

      .shopping-summary table {{
        width: 100%;
        border-collapse: collapse;
        margin-bottom: 16px;
      }}

      .shopping-summary th {{
        text-align: left;
        padding: 10px 12px;
        background: var(--accent-light);
        color: var(--accent);
        font-size: 0.85rem;
        font-weight: bold;
      }}

      .shopping-summary td {{
        padding: 10px 12px;
        border-bottom: 1px solid var(--border);
        font-size: 0.9rem;
      }}

      .shopping-summary .total {{
        text-align: right;
        font-weight: bold;
        color: var(--primary);
        font-size: 1rem;
        margin: 16px 0;
      }}

      .shopping-summary .note {{
        font-size: 0.8rem;
        color: var(--text-light);
        line-height: 1.6;
      }}

      footer {{
        text-align: center;
        padding: 32px 0;
        color: var(--text-light);
        font-size: 0.8rem;
        border-top: 1px solid var(--border);
        margin-top: 40px;
      }}

      @media (max-width: 768px) {{
        .source-grid {{
          grid-template-columns: 1fr;
        }}

        .recipe-card {{
          grid-template-columns: 1fr;
        }}

        .recipe-card img {{
          height: 220px;
          min-height: auto;
        }}

        header h1 {{
          font-size: 1.5rem;
        }}
      }}
    </style>
  </head>
  <body>
    <header>
      <div class="container">
        <h1>Fridge Flyer</h1>
        <p>冷蔵庫の食材 x チラシの特売品で、今日のレシピを提案</p>
      </div>
    </header>

    <main class="container">
      <!-- 入力ソース -->
      <section>
        <h2 class="section-title">入力ソース</h2>
        <div class="source-grid">
          <div class="source-card">
            <img src="../fridge.jpg" alt="冷蔵庫の中身" />
            <div class="card-body" data-type="fridge">
              <h3>冷蔵庫の中身</h3>
              <p>冷蔵庫の食材を分析しました</p>
            </div>
          </div>
          <div class="source-card">
            <img src="../flyer.jpg" alt="チラシ" />
            <div class="card-body" data-type="flyer">
              <h3>スーパーのチラシ</h3>
              <p>チラシの特売品を分析しました</p>
            </div>
          </div>
        </div>
      </section>

      <!-- レシピ提案 -->
      <section>
        <h2 class="section-title">レシピ提案</h2>

        <div class="tag-legend">
          <span><span class="dot fridge"></span> 冷蔵庫の食材</span>
          <span><span class="dot flyer"></span> 買い足し（チラシ特売品）</span>
        </div>

        <div class="recipe-list">
{recipe_section}
        </div>
      </section>
{shopping_html}
    </main>

    <!-- Image Modal -->
    <div class="modal-overlay" id="modal" onclick="this.classList.remove('active')">
      <img id="modal-img" src="" alt="" />
    </div>

    <!-- Text Modal -->
    <div class="text-modal-overlay" id="text-modal">
      <div class="text-modal-content">
        <span class="close-btn" onclick="document.getElementById('text-modal').classList.remove('active')">&times;</span>
        <div id="text-modal-body"></div>
      </div>
    </div>

    <script>
      // 画像モーダル
      document.querySelectorAll('.source-card img').forEach(function(img) {{
        img.addEventListener('click', function() {{
          var modal = document.getElementById('modal');
          var modalImg = document.getElementById('modal-img');
          modalImg.src = this.src;
          modalImg.alt = this.alt;
          modal.classList.add('active');
        }});
      }});

      // Markdownの説明を埋め込み
      var descriptions = {{
        fridge: `{fridge_desc_escaped}`,
        flyer: `{flyer_desc_escaped}`
      }};

      // 簡易Markdown→HTML変換
      function markdownToHtml(md) {{
        if (!md) return '<p>データがありません</p>';
        var html = md;

        // 見出し
        html = html.replace(/^### (.+)$/gm, '<h3>$1</h3>');
        html = html.replace(/^## (.+)$/gm, '<h2>$1</h2>');
        html = html.replace(/^# (.+)$/gm, '<h1>$1</h1>');

        // テーブル
        var lines = html.split('\\n');
        var inTable = false;
        var tableHtml = '';
        var result = [];

        for (var i = 0; i < lines.length; i++) {{
          var line = lines[i];
          if (line.match(/^\\|.+\\|$/)) {{
            if (!inTable) {{
              inTable = true;
              tableHtml = '<table>';
            }}
            if (line.match(/^\\|[-:\\s|]+\\|$/)) {{
              continue;
            }}
            var cells = line.split('|').filter(function(c) {{ return c.trim() !== ''; }});
            var isHeader = i > 0 && lines[i - 1] && !lines[i - 1].match(/^\\|[-:\\s|]+\\|$/) && !lines[i + 1];
            if (i === 0 || (i > 0 && !lines[i - 1].match(/^\\|.+\\|$/))) {{
              tableHtml += '<thead><tr>';
              cells.forEach(function(c) {{ tableHtml += '<th>' + c.trim() + '</th>'; }});
              tableHtml += '</tr></thead><tbody>';
            }} else {{
              tableHtml += '<tr>';
              cells.forEach(function(c) {{ tableHtml += '<td>' + c.trim() + '</td>'; }});
              tableHtml += '</tr>';
            }}
          }} else {{
            if (inTable) {{
              tableHtml += '</tbody></table>';
              result.push(tableHtml);
              tableHtml = '';
              inTable = false;
            }}
            result.push(line);
          }}
        }}
        if (inTable) {{
          tableHtml += '</tbody></table>';
          result.push(tableHtml);
        }}
        html = result.join('\\n');

        // 太字
        html = html.replace(/\\*\\*(.+?)\\*\\*/g, '<strong>$1</strong>');

        // 水平線
        html = html.replace(/^---$/gm, '<hr>');

        // 段落
        html = html.replace(/\\n\\n/g, '</p><p>');
        html = '<p>' + html + '</p>';
        html = html.replace(/<p><(h[123]|table|hr)/g, '<$1');
        html = html.replace(/<\\/(h[123]|table)><\\/p>/g, '</$1>');
        html = html.replace(/<hr><\\/p>/g, '<hr>');
        html = html.replace(/<p><\\/p>/g, '');

        return html;
      }}

      // テキストモーダル
      document.querySelectorAll('.source-card .card-body').forEach(function(body) {{
        body.addEventListener('click', function(e) {{
          e.stopPropagation();
          var type = this.getAttribute('data-type');
          var md = descriptions[type] || '';
          var textModal = document.getElementById('text-modal');
          var textBody = document.getElementById('text-modal-body');
          textBody.innerHTML = markdownToHtml(md);
          textModal.classList.add('active');
        }});
      }});

      // テキストモーダルの背景クリックで閉じる
      document.getElementById('text-modal').addEventListener('click', function(e) {{
        if (e.target === this) {{
          this.classList.remove('active');
        }}
      }});
    </script>

    <footer>
      <div class="container">
        <p>Fridge Flyer &mdash; Powered by Amazon Bedrock Flow</p>
      </div>
    </footer>
  </body>
</html>
'''
    return html


def main() -> None:
    """メイン処理"""
    print("=" * 60)
    print("Fridge Flyer - レシピ生成スクリプト")
    print("=" * 60)

    # AWSクライアント初期化
    s3_client = boto3.client("s3", region_name=REGION)
    # Flowは処理に数分かかるため、タイムアウトを10分に設定
    bedrock_config = Config(read_timeout=600, connect_timeout=60, retries={"max_attempts": 0})
    bedrock_agent_runtime = boto3.client(
        "bedrock-agent-runtime", region_name=REGION, config=bedrock_config
    )

    # 1. 画像をS3にアップロード
    upload_images_to_s3(s3_client)

    # 2. Bedrock Flowを実行
    result_text = invoke_bedrock_flow(bedrock_agent_runtime)

    # 3. 結果をresults/result.mdに保存
    save_result_md(result_text)

    # 4. S3から結果ファイルをダウンロード
    download_results_from_s3(s3_client)

    # 5. レシピをパースしてHTMLを生成
    print("HTMLを生成中...")
    recipe_data = parse_recipe_markdown(result_text)
    html_content = generate_html(recipe_data)

    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    output_path = OUTPUT_DIR / "index.html"
    output_path.write_text(html_content, encoding="utf-8")
    print(f"  - HTMLを保存: {output_path}")

    print("=" * 60)
    print("完了！")
    print(f"  - レシピ: {RESULTS_DIR / 'result.md'}")
    print(f"  - HTML: {output_path}")
    print("=" * 60)

    # 6. ブラウザでHTMLを開く
    print("ブラウザでHTMLを開いています...")
    webbrowser.open(f"file://{output_path.resolve()}")


if __name__ == "__main__":
    main()
