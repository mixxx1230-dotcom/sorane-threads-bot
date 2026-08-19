"""
スケジュール投稿スクリプト
環境変数 SLOT に "noon" または "evening" を渡して実行
START_DATE: 運用開始日（YYYY-MM-DD）
"""
import os
import sys
import requests
from datetime import date, datetime

import json

from posts_data import POSTS

SLOT = os.environ.get("SLOT", "").strip()
if SLOT not in ("noon", "evening"):
    print(f"エラー: SLOT に 'noon' または 'evening' を設定してください（現在: '{SLOT}'）")
    sys.exit(1)

ACCESS_TOKEN = os.environ.get("THREADS_ACCESS_TOKEN", "").strip()
USER_ID = os.environ.get("THREADS_USER_ID", "").strip()
START_DATE_STR = os.environ.get("START_DATE", "2026-08-19")

if not ACCESS_TOKEN or not USER_ID:
    print("エラー: THREADS_ACCESS_TOKEN または THREADS_USER_ID が設定されていません")
    sys.exit(1)

# 今日が何日目かを計算し、7日でループ
start = date.fromisoformat(START_DATE_STR)
today = date.today()
day_index = (today - start).days % len(POSTS)

post_data = POSTS[day_index]
text = post_data[SLOT]

# アプリで設定した上書きデータ（文章・画像URL）を読み込む
OVERRIDE_FILE = os.path.join(os.path.dirname(__file__), "..", "data", "posts_override.json")
image_url = None
if os.path.exists(OVERRIDE_FILE):
    with open(OVERRIDE_FILE) as f:
        overrides = json.load(f)
    if day_index < len(overrides):
        slot_data = overrides[day_index].get(SLOT, {})
        text = slot_data.get("text", text)
        image_url = slot_data.get("imageUrl")

print(f"今日: {today} / 開始日: {start} / day_index: {day_index} / slot: {SLOT}")
print(f"画像URL: {image_url or 'なし'}")
print(f"投稿内容:\n{text}\n")

# Step 1: コンテナ作成
container_params = {
    "text": text,
    "access_token": ACCESS_TOKEN,
}
if image_url:
    container_params["media_type"] = "IMAGE"
    container_params["image_url"] = image_url
else:
    container_params["media_type"] = "TEXT"

res = requests.post(
    f"https://graph.threads.net/v1.0/{USER_ID}/threads",
    data=container_params,
)
result = res.json()

if "id" not in result:
    print(f"エラー（コンテナ作成）: {result}")
    sys.exit(1)

container_id = result["id"]
print(f"コンテナ作成成功: {container_id}")

# Step 2: 公開
import time
time.sleep(5)

res2 = requests.post(
    f"https://graph.threads.net/v1.0/{USER_ID}/threads_publish",
    data={
        "creation_id": container_id,
        "access_token": ACCESS_TOKEN,
    }
)
result2 = res2.json()

if "id" not in result2:
    print(f"エラー（公開）: {result2}")
    sys.exit(1)

print(f"投稿成功！ post_id: {result2['id']}")
