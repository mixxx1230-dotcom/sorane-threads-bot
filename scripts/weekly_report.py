"""
週次インサイトレポート
毎週月曜朝に先週の投稿パフォーマンスを集計してGitHub Issueで通知
"""
import os
import sys
import requests
from datetime import datetime, timezone, timedelta

ACCESS_TOKEN = os.environ.get("THREADS_ACCESS_TOKEN", "").strip()
USER_ID = os.environ.get("THREADS_USER_ID", "").strip()
GITHUB_TOKEN = os.environ.get("GITHUB_TOKEN", "").strip()
GITHUB_REPO = os.environ.get("GITHUB_REPO", "mixxx1230-dotcom/sorane-threads-bot")

if not ACCESS_TOKEN or not USER_ID:
    print("エラー: THREADS_ACCESS_TOKEN または THREADS_USER_ID が設定されていません")
    sys.exit(1)

JST = timezone(timedelta(hours=9))
now_jst = datetime.now(JST)


def get_posts():
    """過去7日間の投稿を取得"""
    since = now_jst - timedelta(days=7)
    since_unix = int(since.timestamp())

    res = requests.get(
        f"https://graph.threads.net/v1.0/{USER_ID}/threads",
        params={
            "fields": "id,text,timestamp,media_type",
            "since": since_unix,
            "access_token": ACCESS_TOKEN,
            "limit": 50,
        }
    )
    data = res.json()
    if "error" in data:
        print(f"投稿取得エラー: {data}")
        return []
    return data.get("data", [])


def get_insights(media_id):
    """投稿のインサイトを取得"""
    res = requests.get(
        f"https://graph.threads.net/v1.0/{media_id}/insights",
        params={
            "metric": "views,likes,replies,reposts,quotes",
            "access_token": ACCESS_TOKEN,
        }
    )
    data = res.json()
    result = {}
    for item in data.get("data", []):
        if "total_value" in item:
            result[item["name"]] = item["total_value"].get("value", 0)
        elif "values" in item and item["values"]:
            result[item["name"]] = item["values"][0].get("value", 0)
        else:
            result[item["name"]] = 0
    return result


def format_text(text, max_len=60):
    if not text:
        return "(テキストなし)"
    text = text.replace("\n", " ")
    if len(text) > max_len:
        return text[:max_len] + "..."
    return text


def format_timestamp(ts_str):
    try:
        dt = datetime.fromisoformat(ts_str.replace("Z", "+00:00"))
        return dt.astimezone(JST).strftime("%m/%d %H:%M")
    except Exception:
        return ts_str


def main():
    print("投稿データを取得中...")
    posts = get_posts()

    if not posts:
        print("先週の投稿が見つかりませんでした")
        return

    print(f"取得した投稿数: {len(posts)}")

    results = []
    for post in posts:
        if post.get("media_type") == "REPOST_FACADE":
            continue

        insights = get_insights(post["id"])
        results.append({
            "id": post["id"],
            "text": post.get("text", ""),
            "timestamp": post.get("timestamp", ""),
            "views": insights.get("views", 0),
            "likes": insights.get("likes", 0),
            "replies": insights.get("replies", 0),
            "reposts": insights.get("reposts", 0),
            "quotes": insights.get("quotes", 0),
        })
        print(f"  {format_text(post.get('text', ''), 30)} → views: {insights.get('views', 0)}")

    if not results:
        print("有効な投稿がありませんでした")
        return

    total_views = sum(r["views"] for r in results)
    total_likes = sum(r["likes"] for r in results)
    total_replies = sum(r["replies"] for r in results)
    total_reposts = sum(r["reposts"] for r in results)

    top_views = sorted(results, key=lambda x: x["views"], reverse=True)[:3]
    top_replies = sorted(results, key=lambda x: x["replies"], reverse=True)[:3]

    week_str = (now_jst - timedelta(days=7)).strftime("%m/%d") + "〜" + (now_jst - timedelta(days=1)).strftime("%m/%d")

    report = f"""## 📊 Sorane Threads 週次レポート（{week_str}）

### 先週の合計
| 指標 | 数値 |
|------|------|
| 👁 インプレッション | {total_views:,} |
| ❤️ いいね | {total_likes:,} |
| 💬 返信 | {total_replies:,} |
| 🔁 リポスト | {total_reposts:,} |
| 📝 投稿数 | {len(results)} |

---

### 🏆 インプTOP3
"""
    for i, r in enumerate(top_views, 1):
        report += f"""
**{i}位** `{format_timestamp(r['timestamp'])}` 👁 {r['views']:,} ❤️ {r['likes']} 💬 {r['replies']}
> {format_text(r['text'])}
"""

    report += "\n---\n\n### 💬 返信が多かった投稿TOP3\n"
    for i, r in enumerate(top_replies, 1):
        report += f"""
**{i}位** `{format_timestamp(r['timestamp'])}` 💬 {r['replies']} 👁 {r['views']:,}
> {format_text(r['text'])}
"""

    report += f"\n\n*生成日時: {now_jst.strftime('%Y-%m-%d %H:%M')} JST*"

    print("\n=== レポート ===")
    print(report)

    if not GITHUB_TOKEN:
        print("GITHUB_TOKEN が未設定のため、Issueは作成されません")
        return

    res = requests.post(
        f"https://api.github.com/repos/{GITHUB_REPO}/issues",
        headers={
            "Authorization": f"Bearer {GITHUB_TOKEN}",
            "Accept": "application/vnd.github+json",
            "X-GitHub-Api-Version": "2022-11-28",
        },
        json={
            "title": f"📊 週次レポート {week_str}",
            "body": report,
        }
    )
    result = res.json()
    if "html_url" in result:
        print(f"\nGitHub Issue作成成功: {result['html_url']}")
    else:
        print(f"GitHub Issue作成失敗: {result}")


if __name__ == "__main__":
    main()
