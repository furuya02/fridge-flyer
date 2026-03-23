#!/usr/bin/env python3
"""
レシピ生成スクリプト
冷蔵庫・チラシ画像をアップロードし、Bedrock Flowでレシピを生成し、HTMLを出力する
"""
import json
import os
import re
import webbrowser
import boto3
from botocore.config import Config
from pathlib import Path
from typing import Any

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


def upload_images_to_s3(s3_client: Any) -> None:
    """画像をS3にアップロードする"""
    print("画像をS3にアップロード中...")

    # flyer.jpg
    if FLYER_PATH.exists():
        s3_client.upload_file(str(FLYER_PATH), BUCKET_NAME, "flyer.jpg")
        print(f"  - {FLYER_PATH.name} -> s3://{BUCKET_NAME}/flyer.jpg")
    else:
        print(f"  - 警告: {FLYER_PATH} が見つかりません")

    # fridge.jpg
    if FRIDGE_PATH.exists():
        s3_client.upload_file(str(FRIDGE_PATH), BUCKET_NAME, "fridge.jpg")
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

    # テーブル形式の買い物リストを抽出
    table_match = re.search(
        r"## .*お買い物まとめ.*\n\n\|.+\|.+\|\n\|[-\s|]+\|\n((?:\|.+\|.+\|\n)+)",
        md_text,
        re.DOTALL,
    )
    if table_match:
        for line in table_match.group(1).strip().split("\n"):
            cols = [c.strip() for c in line.split("|") if c.strip()]
            if len(cols) >= 2:
                item_name = cols[0].replace("**", "")
                price = cols[1].replace("**", "")
                if "合計" in item_name.lower():
                    shopping_summary["total"] = price
                else:
                    shopping_summary["items"].append({"name": item_name, "price": price})

    # 注記を抽出
    note_match = re.search(r"> ※(.+?)(?=\n\n|\Z)", md_text, re.DOTALL)
    if note_match:
        shopping_summary["note"] = note_match.group(1).strip()

    # 最後のメッセージを抽出
    final_msg_match = re.search(r"\n\nたった\*\*(.+?)\*\*で.+", md_text)
    if final_msg_match:
        shopping_summary["final_message"] = final_msg_match.group(0).strip()

    return {"recipes": recipes, "shopping_summary": shopping_summary}


def generate_html(recipe_data: dict[str, Any]) -> str:
    """レシピデータからHTMLを生成する"""
    recipes = recipe_data.get("recipes", [])
    shopping_summary = recipe_data.get("shopping_summary", {})

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
        items_rows = ""
        for item in shopping_summary.get("items", []):
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

        shopping_html = f"""
      <!-- お買い物まとめ -->
      <section>
        <h2 class="section-title">お買い物まとめ</h2>
        <div class="shopping-summary">
          <h3>チラシから買い足す商品</h3>
          <table>
            <thead>
              <tr>
                <th>買い足し品</th>
                <th>価格（税込）</th>
              </tr>
            </thead>
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
            <div class="card-body">
              <h3>冷蔵庫の中身</h3>
              <p>冷蔵庫の食材を分析しました</p>
            </div>
          </div>
          <div class="source-card">
            <img src="../flyer.jpg" alt="チラシ" />
            <div class="card-body">
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

    <script>
      document.querySelectorAll('.source-card img').forEach(function(img) {{
        img.addEventListener('click', function() {{
          var modal = document.getElementById('modal');
          var modalImg = document.getElementById('modal-img');
          modalImg.src = this.src;
          modalImg.alt = this.alt;
          modal.classList.add('active');
        }});
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
