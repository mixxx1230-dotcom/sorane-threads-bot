# -*- coding: utf-8 -*-
"""
朝8:00の空き枠投稿スクリプト
TIME_SLOTS 例: "15:00~ 17:00~ 18:00~" (スペース・読点・中点・改行 いずれでも可)
テンプレートは data/morning_template.txt で上書き可能
"""
import os
import sys
import re
import time
import requests
from datetime import datetime, timezone, timedelta

ACCESS_TOKEN = os.environ.get("THREADS_ACCESS_TOKEN", "").strip()
USER_ID      = os.environ.get("THREADS_USER_ID", "").strip()
TIME_SLOTS   = os.environ.get("TIME_SLOTS", "").strip()

if not ACCESS_TOKEN or not USER_ID:
    print("ERROR: THREADS_ACCESS_TOKEN or THREADS_USER_ID is not set")
    sys.exit(1)

if not TIME_SLOTS:
    print("TIME_SLOTS is empty, skipping")
    sys.exit(0)

# 今日の日付（JST）
JST = timezone(timedelta(hours=9))
now = datetime.now(JST)
date_str = f"{now.month}/{now.day}"
weekdays = ["月", "火", "水", "木", "金", "土", "日"]
weekday = weekdays[now.weekday()]

# 空き枠を分割（・ / 、 / , / スペース複数 / 改行 に対応）
raw = TIME_SLOTS
raw = re.sub(r'[・\u30FB\uFF65,\uFF0C\u3001/\uFF0F]+', '\n', raw)
raw = re.sub(r'[ \t]{2,}', '\n', raw)
slots = [s.strip() for s in raw.split('\n') if s.strip()]

if not slots:
    print("ERROR: no slots parsed from TIME_SLOTS:", TIME_SLOTS)
    sys.exit(1)

slots_lines = "\n".join(f"・{s}" for s in slots)

# テンプレート読み込み（data/morning_template.txt があれば優先）
TEMPLATE_FILE = os.path.join(os.path.dirname(__file__), "..", "data", "morning_template.txt")

if os.path.exists(TEMPLATE_FILE):
    with open(TEMPLATE_FILE, encoding="utf-8") as f:
        template = f.read()
    text = (
        template
        .replace("{date}", date_str)
        .replace("{weekday}", weekday)
        .replace("{slots}", slots_lines)
    )
else:
    # デフォルトテンプレート
    text = (
        f"＼おはようございます☀／\n\n"
        f"本日の空き状況🌿\n"
        f"【{date_str}（{weekday}）】\n"
        f"{slots_lines}\n\n"
        f"当日予約も大歓迎です◎\n"
        f"頭の重さ・眼精疲労・首肩こり・睡眠のお悩みに。\n"
        f"完全個室の落ち着いた空間で、ゆっくりお過ごしください😌\n\n"
        f"📍住所\n"
        f"大阪府大阪市中央区西心斎橋1丁目9-28\n"
        f"リーストラクチャー西心斎橋307 Sorane心斎橋店\n\n"
        f"▼WEBご予約はこちら💁\n"
        f"https://beauty.hotpepper.jp/kr/slnH000803720/\n\n"
        f"※施術中はお電話に出られない場合がございます。\n"
        f"ネット予約または公式LINEからのご連絡がおすすめです🙆"
    )

print("投稿内容:")
print(text)
print()

# Step 1: コンテナ作成（params= でUTF-8を確実に渡す）
res = requests.post(
    f"https://graph.threads.net/v1.0/{USER_ID}/threads",
    params={
        "media_type": "TEXT",
        "text": text,
        "access_token": ACCESS_TOKEN,
    }
)
result = res.json()
print("Container response:", result)

if "id" not in result:
    print("ERROR (container):", result)
    sys.exit(1)

container_id = result["id"]
print("Container OK:", container_id)
time.sleep(5)

# Step 2: 公開
res2 = requests.post(
    f"https://graph.threads.net/v1.0/{USER_ID}/threads_publish",
    params={
        "creation_id": container_id,
        "access_token": ACCESS_TOKEN,
    }
)
result2 = res2.json()
print("Publish response:", result2)

if "id" not in result2:
    print("ERROR (publish):", result2)
    sys.exit(1)

print("SUCCESS post_id:", result2["id"])
