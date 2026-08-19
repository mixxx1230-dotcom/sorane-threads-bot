"""
朝8:00の空き枠投稿スクリプト
環境変数 TIME_SLOTS に空き枠の時間を渡す
例: TIME_SLOTS="15:00〜・17:00〜・18:00〜"
"""
import os
import sys
import requests
from datetime import datetime, timezone, timedelta

ACCESS_TOKEN = os.environ.get("THREADS_ACCESS_TOKEN", "").strip()
USER_ID = os.environ.get("THREADS_USER_ID", "").strip()
TIME_SLOTS = os.environ.get("TIME_SLOTS", "").strip()

if not ACCESS_TOKEN or not USER_ID:
    print("エラー: THREADS_ACCESS_TOKEN または THREADS_USER_ID が設定されていません")
    sys.exit(1)

if not TIME_SLOTS:
    print("TIME_SLOTS が空のためスキップします")
    sys.exit(0)

# 今日の日付（JST）
JST = timezone(timedelta(hours=9))
now = datetime.now(JST)
date_str = f"{now.month}/{now.day}"
weekdays = ["月", "火", "水", "木", "金", "土", "日"]
weekday = weekdays[now.weekday()]

# 空き枠を箇条書きに整形
slots = [s.strip() for s in TIME_SLOTS.replace("、", "\n").replace(",", "\n").split("\n") if s.strip()]
slots_text = "\n".join(f"・{s}" for s in slots)

text = (
    f"＼おはようございます☀／\n\n"
    f"本日の空き状況🌿\n"
    f"【{date_str}（{weekday}）】\n"
    f"{slots_text}\n\n"
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

print(f"投稿内容:\n{text}\n")

# Step 1: コンテナ作成
res = requests.post(
    f"https://graph.threads.net/v1.0/{USER_ID}/threads",
    data={
        "media_type": "TEXT",
        "text": text,
        "access_token": ACCESS_TOKEN,
    }
)
result = res.json()

if "id" not in result:
    print(f"エラー（コンテナ作成）: {result}")
    sys.exit(1)

container_id = result["id"]
print(f"コンテナ作成成功: {container_id}")

import time
time.sleep(5)

# Step 2: 公開
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
