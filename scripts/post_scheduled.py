"""
スケジュール投稿スクリプト
環境変数 SLOT に "noon" または "evening" を渡して実行
START_DATE: 運用開始日（YYYY-MM-DD）
TARGET_DATE: 復旧対象日（YYYY-MM-DD、省略時はJST当日）
"""
import os
import sys
import time
import requests
from datetime import date, datetime, timezone, timedelta

import json

from posts_data import POSTS

SLOT = os.environ.get("SLOT", "").strip()
if SLOT not in ("noon", "evening"):
    print(f"エラー: SLOT に 'noon' または 'evening' を設定してください（現在: '{SLOT}'）")
    sys.exit(1)

ACCESS_TOKEN = os.environ.get("THREADS_ACCESS_TOKEN", "").strip()
USER_ID = os.environ.get("THREADS_USER_ID", "").strip()
START_DATE_STR = os.environ.get("START_DATE", "2026-08-19")
GITHUB_REPO = "mixxx1230-dotcom/sorane-threads-bot"
GITHUB_BRANCH = "main"

if not ACCESS_TOKEN or not USER_ID:
    print("エラー: THREADS_ACCESS_TOKEN または THREADS_USER_ID が設定されていません")
    sys.exit(1)

# 日付はJST基準で計算（GitHub ActionsはUTC環境）
JST = timezone(timedelta(hours=9))
today = datetime.now(JST).date()
target_date_str = os.environ.get("TARGET_DATE", "").strip()
target_date = date.fromisoformat(target_date_str) if target_date_str else today
if target_date > today:
    print(f"エラー: 未来日は投稿できません ({target_date})")
    sys.exit(1)
start = date.fromisoformat(START_DATE_STR)
day_index = (target_date - start).days % len(POSTS)

post_data = POSTS[day_index]
text = post_data[SLOT]

# アプリで設定した上書きデータ（文章・画像URL）を読み込む
OVERRIDE_FILE = os.path.join(os.path.dirname(__file__), "..", "data", "posts_override.json")
image_url = None
override_used = False
topic_tag = "BEAUTY_FASHION"

if os.path.exists(OVERRIDE_FILE):
    with open(OVERRIDE_FILE) as f:
        overrides = json.load(f)
    if day_index < len(overrides):
        slot_data = overrides[day_index].get(SLOT, {})
        if slot_data.get("text"):
            text = slot_data["text"]
            override_used = True
        # 投稿内容ごとにコミュニティを切り替える。未設定は従来値を使用。
        raw_topic_tag = slot_data.get("communityTag")
        if raw_topic_tag is not None:
            topic_tag = str(raw_topic_tag).strip()
        raw_image = slot_data.get("imageUrl")
        if raw_image:
            # /uploads/filename → GitHub raw URL に変換
            if raw_image.startswith("/uploads/"):
                filename = os.path.basename(raw_image)
                image_url = f"https://raw.githubusercontent.com/{GITHUB_REPO}/{GITHUB_BRANCH}/images/{filename}"
                print(f"画像URL変換: {raw_image} → {image_url}")
            else:
                image_url = raw_image
else:
    print("警告: posts_override.json が見つかりません。デフォルトテキストを使用します。")
    print("  → sorane-appで「GitHubに同期」ボタンを押してください。")

print(f"=== 投稿情報 ===")
print(f"JST今日: {today} / 対象日: {target_date} / 開始日: {start} / day_index: {day_index} / slot: {SLOT}")
print(f"override使用: {override_used}")
print(f"画像URL: {image_url or 'なし（テキスト投稿）'}")
print(f"コミュニティ: {topic_tag or 'なし'}")
print(f"投稿内容:\n{text}\n")
print("===============")


# 通常実行と復旧実行が近接しても二重投稿しない
HISTORY_FILE = os.path.join(os.path.dirname(__file__), "..", "data", "post_history.json")
history = {}
if os.path.exists(HISTORY_FILE):
    with open(HISTORY_FILE, encoding="utf-8") as f:
        try:
            history = json.load(f)
        except (json.JSONDecodeError, OSError):
            history = {}

history_key = f"{target_date}_{SLOT}"
if history_key in history:
    print(f"投稿済みのためスキップ: {history_key}")
    sys.exit(0)

def post_container(use_image):
    """コンテナ作成。use_image=Falseでテキスト投稿にフォールバック"""
    params = {"text": text, "access_token": ACCESS_TOKEN}
    if topic_tag:
        params["topic_tag"] = topic_tag
    if use_image and image_url:
        params["media_type"] = "IMAGE"
        params["image_url"] = image_url
    else:
        params["media_type"] = "TEXT"
    res = requests.post(
        f"https://graph.threads.net/v1.0/{USER_ID}/threads",
        params=params,
    )
    return res.json()

# Step 1: コンテナ作成（画像付きで試みる）
result = post_container(use_image=True)

# 画像エラー時はテキスト投稿にフォールバック
if "id" not in result and image_url:
    print(f"画像付き投稿失敗: {result}")
    print("テキスト投稿にフォールバックします...")
    result = post_container(use_image=False)

if "id" not in result:
    print(f"エラー（コンテナ作成）: {result}")
    sys.exit(1)

container_id = result["id"]
print(f"コンテナ作成成功: {container_id}")

# Step 2: 公開
time.sleep(5)

res2 = requests.post(
    f"https://graph.threads.net/v1.0/{USER_ID}/threads_publish",
    params={
        "creation_id": container_id,
        "access_token": ACCESS_TOKEN,
    }
)
result2 = res2.json()

if "id" not in result2:
    print(f"エラー（公開）: {result2}")
    sys.exit(1)

print(f"投稿成功！ post_id: {result2['id']}")

# 投稿履歴を記録
os.makedirs(os.path.dirname(HISTORY_FILE), exist_ok=True)
history[history_key] = {
    "posted_at": datetime.now(JST).isoformat(),
    "post_id": result2["id"],
    "day_index": day_index,
    "target_date": str(target_date),
}

with open(HISTORY_FILE, "w") as f:
    json.dump(history, f, indent=2, ensure_ascii=False)

print(f"投稿履歴を記録: {history_key}")
