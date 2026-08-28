"""Hot Pepper Beautyの最新ブログを検知し、新着だけThreadsで告知する。"""
import html
import json
import os
import re
import sys
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path
from urllib.parse import urljoin

import requests

BLOG_LIST_URL = "https://beauty.hotpepper.jp/kr/slnH000803720/blog/"
ROOT = Path(__file__).resolve().parent.parent
STATE_FILE = ROOT / "data" / "hotpepper_blog_state.json"
ACCESS_TOKEN = os.environ.get("THREADS_ACCESS_TOKEN", "").strip()
USER_ID = os.environ.get("THREADS_USER_ID", "").strip()
AUTOMATION_START_DATE = os.environ.get("AUTOMATION_START_DATE", "2026-08-29")


def latest_blog():
    response = requests.get(
        BLOG_LIST_URL,
        headers={"User-Agent": "Mozilla/5.0 (Sorane blog update checker)"},
        timeout=30,
    )
    response.raise_for_status()
    # 一覧は新着順。最初の記事リンクを取得する。
    pattern = re.compile(
        r'<a[^>]+href=["\']([^"\']*/blog/bidA\d+\.html[^"\']*)["\'][^>]*>(.*?)</a>',
        re.IGNORECASE | re.DOTALL,
    )
    for href, raw_title in pattern.findall(response.text):
        title = html.unescape(re.sub(r"<[^>]+>", "", raw_title)).strip()
        title = re.sub(r"\s+", " ", title)
        if title:
            item = {"url": urljoin(BLOG_LIST_URL, href), "title": title}
            item["image_url"] = article_image(item["url"])
            return item
    raise RuntimeError("ブログ一覧から最新記事を取得できませんでした")


def article_image(article_url):
    """記事本文の投稿画像を取得。決済バナーやロゴは対象外。"""
    response = requests.get(
        article_url,
        headers={"User-Agent": "Mozilla/5.0 (Sorane blog update checker)"},
        timeout=30,
    )
    response.raise_for_status()
    for tag in re.findall(r"<img\b[^>]*>", response.text, re.IGNORECASE):
        src_match = re.search(r'\bsrc=["\']([^"\']+)["\']', tag, re.IGNORECASE)
        if not src_match:
            continue
        src = html.unescape(src_match.group(1))
        if "/IMG_BLOG_ORG_K/" in src:
            return urljoin(article_url, src)
    return None


def load_state():
    if not STATE_FILE.exists():
        return {}
    try:
        return json.loads(STATE_FILE.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return {}


def save_state(item, status):
    STATE_FILE.parent.mkdir(parents=True, exist_ok=True)
    STATE_FILE.write_text(
        json.dumps({**item, "status": status}, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )


def publish(item):
    if not ACCESS_TOKEN or not USER_ID:
        raise RuntimeError("THREADS_ACCESS_TOKEN / THREADS_USER_ID が未設定です")
    text = (
        "ブログを更新しました🌿\n\n"
        f"「{item['title']}」\n\n"
        "ぜひご覧ください✨\n"
        f"{item['url']}"
    )
    params = {
        "media_type": "IMAGE" if item.get("image_url") else "TEXT",
        "text": text,
        "access_token": ACCESS_TOKEN,
    }
    if item.get("image_url"):
        params["image_url"] = item["image_url"]
    created = requests.post(
        f"https://graph.threads.net/v1.0/{USER_ID}/threads",
        params=params,
        timeout=30,
    ).json()
    if "id" not in created:
        raise RuntimeError(f"コンテナ作成失敗: {created}")
    time.sleep(5)
    published = requests.post(
        f"https://graph.threads.net/v1.0/{USER_ID}/threads_publish",
        params={"creation_id": created["id"], "access_token": ACCESS_TOKEN},
        timeout=30,
    ).json()
    if "id" not in published:
        raise RuntimeError(f"公開失敗: {published}")
    return published["id"]


def main():
    today_jst = datetime.now(timezone(timedelta(hours=9))).date()
    if str(today_jst) < AUTOMATION_START_DATE:
        print(f"自動運用開始前のためスキップ: {today_jst}")
        return 0
    item = latest_blog()
    state = load_state()
    force_post = os.environ.get("FORCE_POST", "").strip() == "1"
    print(f"最新ブログ: {item['title']} {item['url']}")
    print(f"記事画像: {item.get('image_url') or 'なし（テキスト投稿へフォールバック）'}")
    if not state and not force_post:
        # 初回は現在の最新記事を基準にし、古い記事を告知しない。
        save_state(item, "baseline")
        print("初回基準を保存（Threads投稿なし）")
        return 0
    if state.get("url") == item["url"] and not force_post:
        print("新着なし")
        return 0
    post_id = publish(item)
    save_state({**item, "threads_post_id": post_id}, "posted")
    print(f"ブログ更新をThreadsに投稿: {post_id}")
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except Exception as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        raise
