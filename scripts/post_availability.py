"""
空き枠をThreadsに投稿するスクリプト
GitHub Actionsの手動実行から TIME_SLOTS 環境変数で時間を受け取ります
"""
import os
import sys
import requests
from datetime import datetime, timedelta, timezone


def post_to_threads(text):
    token = os.environ["THREADS_ACCESS_TOKEN"]
    user_id = os.environ["THREADS_USER_ID"]

    res = requests.post(
        f"https://graph.threads.net/v1.0/{user_id}/threads",
        params={"media_type": "TEXT", "text": text, "access_token": token},
    )
    res.raise_for_status()
    creation_id = res.json()["id"]

    pub = requests.post(
        f"https://graph.threads.net/v1.0/{user_id}/threads_publish",
        params={"creation_id": creation_id, "access_token": token},
    )
    pub.raise_for_status()
    return pub.json()


if __name__ == "__main__":
    slots = os.environ.get("TIME_SLOTS", "").strip()

    if not slots:
        print("エラー: TIME_SLOTS が設定されていません")
        sys.exit(1)

    jst = timezone(timedelta(hours=9))
    today = datetime.now(jst)
    weekdays = ["月", "火", "水", "木", "金", "土", "日"]
    weekday = weekdays[today.weekday()]
    date_str = f"{today.month}月{today.day}日（{weekday}）"

    text = f"""心斎橋で今日ヘッドスパを受けたい方へ。

{date_str}は、こちらの時間にご案内できます。

{slots}

コースに迷っている方は、ご来店後の相談でも大丈夫です。空き状況はプロフィールから確認できます。"""

    result = post_to_threads(text)
    print(f"投稿完了: {result}")
