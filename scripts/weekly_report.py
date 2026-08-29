"""
週次インサイトレポート + AI投稿改善
毎週月曜 9:00 JST に自動実行

処理:
1. 先週の投稿インサイトを取得・分析
2. Claude AIで何が伸びたかを分析し、今後7日間の投稿を改善
3. posts_override.jsonを更新してコミット
4. GitHub Issueで詳細レポートを通知
"""
import os
import sys
import json
import re
import time
import requests
from datetime import datetime, timezone, timedelta, date

sys.path.insert(0, os.path.dirname(__file__))
from posts_data import POSTS
from learning_engine import build_learning_profile, profile_as_prompt

ACCESS_TOKEN = os.environ.get("THREADS_ACCESS_TOKEN", "").strip()
USER_ID = os.environ.get("THREADS_USER_ID", "").strip()
GITHUB_TOKEN = os.environ.get("GITHUB_TOKEN", "").strip()
ANTHROPIC_API_KEY = os.environ.get("ANTHROPIC_API_KEY", "").strip()
ENABLE_EXTERNAL_AI = os.environ.get("ENABLE_EXTERNAL_AI", "false").lower() == "true"
GITHUB_REPO = os.environ.get("GITHUB_REPO", "mixxx1230-dotcom/sorane-threads-bot")
OVERRIDE_FILE = os.path.join(os.path.dirname(__file__), "..", "data", "posts_override.json")
HISTORY_FILE = os.path.join(os.path.dirname(__file__), "..", "data", "insights_history.json")
POST_RECORDS_FILE = os.path.join(os.path.dirname(__file__), "..", "data", "post_performance.json")
LEARNING_PROFILE_FILE = os.path.join(os.path.dirname(__file__), "..", "data", "learning_profile.json")
THREADS_TRENDS_FILE = os.path.join(os.path.dirname(__file__), "..", "data", "threads_trends.json")
START_DATE_STR = os.environ.get("START_DATE", "2026-08-19")

JST = timezone(timedelta(hours=9))
now_jst = datetime.now(JST)
today = now_jst.date()
start = date.fromisoformat(START_DATE_STR)
current_day_index = (today - start).days % len(POSTS)

if not ACCESS_TOKEN or not USER_ID:
    print("エラー: THREADS_ACCESS_TOKEN または THREADS_USER_ID が設定されていません")
    sys.exit(1)


# ── Threads API ──────────────────────────────────────────────

def get_posts():
    since = now_jst - timedelta(days=90)
    url = f"https://graph.threads.net/v1.0/{USER_ID}/threads"
    params = {
        "fields": "id,text,timestamp,media_type,permalink",
        "since": int(since.timestamp()),
        "access_token": ACCESS_TOKEN,
        "limit": 100,
    }
    posts = []
    for _ in range(10):
        res = requests.get(url, params=params, timeout=30)
        data = res.json()
        if "error" in data:
            print(f"投稿取得エラー: {data}")
            break
        posts.extend(data.get("data", []))
        url = data.get("paging", {}).get("next")
        if not url:
            break
        params = None
    return [p for p in posts if p.get("media_type") != "REPOST_FACADE"]


def get_insights(media_id):
    res = requests.get(
        f"https://graph.threads.net/v1.0/{media_id}/insights",
        params={
            "metric": "views,likes,replies,reposts,quotes,shares",
            "access_token": ACCESS_TOKEN,
        }
    )
    result = {}
    for item in res.json().get("data", []):
        if "total_value" in item:
            result[item["name"]] = item["total_value"].get("value", 0)
        elif "values" in item and item["values"]:
            result[item["name"]] = item["values"][0].get("value", 0)
        else:
            result[item["name"]] = 0
    return result


# ── Helpers ──────────────────────────────────────────────────

def fmt(text, max_len=60):
    if not text:
        return "(テキストなし)"
    text = text.replace("\n", " ")
    return text[:max_len] + "..." if len(text) > max_len else text


def fmt_ts(ts_str):
    try:
        dt = datetime.fromisoformat(ts_str.replace("Z", "+00:00"))
        return dt.astimezone(JST).strftime("%m/%d %H:%M")
    except Exception:
        return ts_str


def classify_post(text):
    if not text:
        return "その他"
    if "＼" in text and "／" in text:
        return "問いかけ（＼質問／形式）"
    if any(c in text for c in ["①", "②", "③", "④"]):
        return "問いかけ（選択肢形式）"
    if "心斎橋" in text and any(k in text for k in ["Sorane", "施術", "個室", "お待ち", "ご案内"]):
        return "店舗・地域"
    if "施術" in text and ("感じる" in text or "気づ" in text or "多いです" in text):
        return "施術者目線"
    if any(k in text for k in ["てみてください", "やってみ", "試してみ"]):
        return "セルフケア"
    if any(k in text for k in ["からです", "ています。", "なります。", "なりやすい"]):
        return "知識・解説"
    if any(k in text for k in ["ありませんか", "ませんか", "ますか"]):
        return "共感・習慣改善"
    return "その他"


# ── Google Trends ─────────────────────────────────────────────

TREND_KEYWORDS = [
    "ヘッドスパ",
    "ドライヘッドスパ",
    "マッサージ 大阪",
    "肩こり",
    "頭痛 原因",
    "眼精疲労",
    "睡眠 改善",
    "美容 心斎橋",
]

def get_google_trends():
    """Google Trends APIでキーワードの直近トレンドを取得"""
    try:
        from pytrends.request import TrendReq
        pytrends = TrendReq(hl="ja-JP", tz=540, timeout=(10, 25), retries=2, backoff_factor=0.5)

        trend_results = {}

        # 5キーワードずつAPIに投げる（上限）
        for i in range(0, len(TREND_KEYWORDS), 5):
            batch = TREND_KEYWORDS[i:i+5]
            try:
                pytrends.build_payload(batch, timeframe="now 30-d", geo="JP")
                df = pytrends.interest_over_time()
                if df is not None and not df.empty:
                    for kw in batch:
                        if kw in df.columns:
                            recent = df[kw].iloc[-7:].mean()   # 直近7日平均
                            prev = df[kw].iloc[-14:-7].mean()  # その前7日平均
                            change = ((recent - prev) / max(prev, 1)) * 100
                            trend_results[kw] = {
                                "score": round(float(recent), 1),
                                "change_pct": round(float(change), 1),
                            }
                time.sleep(1)  # レート制限対策
            except Exception as e:
                print(f"  トレンド取得エラー（batch {i}）: {e}")
                continue

        return trend_results

    except ImportError:
        print("pytrends未インストール、トレンド取得をスキップ")
        return {}
    except Exception as e:
        print(f"Google Trendsエラー: {e}")
        return {}


def get_threads_trend_signals(limit_per_keyword=25):
    """個別投稿を保存せず、Threads内のキーワード出現件数だけ集計する。"""
    signals = []
    for keyword in TREND_KEYWORDS:
        try:
            res = requests.get(
                "https://graph.threads.net/v1.0/keyword_search",
                params={
                    "q": keyword,
                    "search_type": "RECENT",
                    "search_mode": "KEYWORD",
                    "fields": "id",
                    "limit": limit_per_keyword,
                    "access_token": ACCESS_TOKEN,
                },
                timeout=30,
            )
            data = res.json()
            if "error" in data:
                print(f"  Threads検索スキップ（{keyword}）: {data['error'].get('message', '権限エラー')}")
                continue
            signals.append({"keyword": keyword, "recent_count": len(data.get("data", []))})
        except requests.RequestException as exc:
            print(f"  Threads検索エラー（{keyword}）: {exc}")
    signals.sort(key=lambda item: item["recent_count"], reverse=True)
    payload = {"generated_at": now_jst.isoformat(), "signals": signals}
    with open(THREADS_TRENDS_FILE, "w") as f:
        json.dump(payload, f, indent=2, ensure_ascii=False)
    return signals


def format_trends_text(trends):
    if not trends:
        return ""
    text = "## 📊 Google Trendsトレンド（直近7日・日本）\n\n"
    text += "| キーワード | スコア | 前週比 |\n"
    text += "|-----------|--------|--------|\n"
    sorted_trends = sorted(trends.items(), key=lambda x: x[1]["score"], reverse=True)
    for kw, data in sorted_trends:
        arrow = "↑" if data["change_pct"] > 5 else ("↓" if data["change_pct"] < -5 else "→")
        text += f"| {kw} | {data['score']} | {arrow} {data['change_pct']:+.0f}% |\n"
    rising = [kw for kw, d in sorted_trends if d["change_pct"] > 10]
    if rising:
        text += f"\n🔥 上昇中: {', '.join(rising)}\n"
    return text


# ── Upcoming posts ────────────────────────────────────────────

def get_upcoming_posts(n=14, start_offset=1):
    upcoming = []
    for offset in range(start_offset, start_offset + n):
        idx = (current_day_index + offset) % len(POSTS)
        day_offset = timedelta(days=offset)
        day_date = today + day_offset
        upcoming.append({
            "day_index": idx,
            "date": day_date.strftime("%m/%d"),
            "noon": POSTS[idx]["noon"],
            "evening": POSTS[idx]["evening"],
        })
    return upcoming


# ── Claude AI ─────────────────────────────────────────────────

GUIDELINES = """
## 投稿スタイルルール（Sorane Threads）
- 改行は文の途中でも入れる（1ブロック1〜2行）
- 絵文字: 問いかけ系は多め、セルフケア・シンプル系は1〜2個
- 問いかけ形式: ＼質問です👀／ ヘッダー + スタッフの回答を開示（例: 「スタッフは①が多めです」）
- 店舗CTA: 「心斎橋にあります🌿」くらい短く自然に
- 禁止: 「ご褒美時間」「癒しの時間」「自律神経を整える」「弊店」「お客様一人ひとり」
- 禁止: 「ゆっくり休みましょう」だけで終わる（ポエム化）
- 毎投稿から予約を取ろうとしない
- 引っかかり → 自分ごと化 → 少し役立つ情報 → 読者が入れる余白
"""

def call_claude(performance_text, upcoming_text, learning_text, trends_text=""):
    if not ANTHROPIC_API_KEY:
        return None

    trends_section = f"\n---\n\n{trends_text}" if trends_text else ""

    prompt = f"""あなたはSoraneというドライヘッドスパ専門店（大阪・心斎橋）のSNS担当です。
Threadsアカウントの投稿を担当しています。

{GUIDELINES}

---

## 先週のThreads投稿パフォーマンス

{performance_text}{trends_section}

---

## 累積学習プロファイル

{learning_text}

---

## 今後7日間の予定投稿

{upcoming_text}

---

上記のパフォーマンスデータ・トレンドをもとに、以下を出力してください。

<analysis>
## 先週の分析

### インプが高かった投稿の共通点
（何が引っかかりを生んだか、具体的に）

### 伸びなかった投稿の問題点
（何が弱かったか）

### 外部トレンドとの関係
（Google Trendsで上昇中のキーワードと、今後の投稿への活かし方）

### 今後の投稿に活かすべきポイント
（具体的に箇条書きで、トレンドキーワードを意識した提案も含む）
</analysis>

<improvements>
今後14日間の未投稿分を上記の分析をもとに改善してください。
改善が必要な投稿だけでOKです（良いものはそのままで）。
過去の勝ちパターンをコピーするのではなく、フック・具体性・会話余地を再利用してください。

以下のJSON形式で出力してください（day_indexとslotとtextのみ）:
[
  {{"day_index": 数字, "slot": "noon", "text": "改善後のテキスト"}},
  {{"day_index": 数字, "slot": "evening", "text": "改善後のテキスト"}}
]
</improvements>
"""

    res = requests.post(
        "https://api.anthropic.com/v1/messages",
        headers={
            "x-api-key": ANTHROPIC_API_KEY,
            "anthropic-version": "2023-06-01",
            "content-type": "application/json",
        },
        json={
            "model": "claude-haiku-4-5-20251001",
            "max_tokens": 4096,
            "messages": [{"role": "user", "content": prompt}],
        }
    )
    data = res.json()
    if "error" in data:
        print(f"Claude APIエラー: {data}")
        return None
    return data["content"][0]["text"]


def parse_claude_response(text):
    analysis = ""
    improvements = []

    analysis_match = re.search(r"<analysis>(.*?)</analysis>", text, re.DOTALL)
    if analysis_match:
        analysis = analysis_match.group(1).strip()

    improvements_match = re.search(r"<improvements>(.*?)</improvements>", text, re.DOTALL)
    if improvements_match:
        raw = improvements_match.group(1).strip()
        json_match = re.search(r"\[.*\]", raw, re.DOTALL)
        if json_match:
            try:
                improvements = json.loads(json_match.group())
            except json.JSONDecodeError as e:
                print(f"JSON解析エラー: {e}")

    return analysis, improvements


# ── Override JSON ─────────────────────────────────────────────

def load_override():
    if os.path.exists(OVERRIDE_FILE):
        with open(OVERRIDE_FILE) as f:
            try:
                return json.load(f)
            except Exception:
                pass
    return []


def apply_improvements(improvements, allowed_indices):
    override = load_override()
    changed = []

    for imp in improvements:
        idx = imp.get("day_index")
        slot = imp.get("slot")
        text = imp.get("text", "").strip()

        if idx is None or not slot or not text:
            continue

        if idx not in allowed_indices:
            print(f"  スキップ（未投稿期間外）: day_index={idx} slot={slot}")
            continue

        # 配列を必要な長さに拡張（空エントリで埋める）
        while len(override) <= idx:
            override.append({
                "morning": {"timeSlots": ""},
                "noon": {},
                "evening": {}
            })

        # テキストのみ更新（他フィールドはdefaultから取得）
        if slot in ("noon", "evening"):
            override[idx][slot]["text"] = text
            changed.append({"day_index": idx, "slot": slot})
            print(f"  更新: day_index={idx} slot={slot}")

    if changed:
        with open(OVERRIDE_FILE, "w") as f:
            json.dump(override, f, indent=2, ensure_ascii=False)
        print(f"posts_override.jsonを更新しました（{len(changed)}件）")

    return changed


# ── History ───────────────────────────────────────────────────

def save_history(week_str, results, type_stats, analysis):
    if os.path.exists(HISTORY_FILE):
        with open(HISTORY_FILE) as f:
            try:
                history = json.load(f)
            except Exception:
                history = []
    else:
        history = []

    # 同じ週のデータがあれば上書き
    history = [h for h in history if h.get("week") != week_str]

    total_views = sum(r["views"] for r in results)
    total_likes = sum(r["likes"] for r in results)
    total_replies = sum(r["replies"] for r in results)

    record = {
        "week": week_str,
        "recorded_at": now_jst.strftime("%Y-%m-%d %H:%M"),
        "totals": {
            "views": total_views,
            "likes": total_likes,
            "replies": total_replies,
            "posts": len(results),
        },
        "type_stats": {
            t: {
                "count": s["count"],
                "avg_views": s["views"] // max(s["count"], 1),
                "avg_replies": round(s["replies"] / max(s["count"], 1), 2),
            }
            for t, s in type_stats.items()
        },
        "top_post": max(results, key=lambda x: x["views"], default={}),
        "ai_summary": analysis[:500] if analysis else "",
    }

    history.append(record)
    # 最新26週（半年分）だけ保持
    history = history[-26:]

    with open(HISTORY_FILE, "w") as f:
        json.dump(history, f, indent=2, ensure_ascii=False)
    print(f"insights_history.jsonに保存しました（累計{len(history)}週）")
    return history


def build_trend_text(history):
    if len(history) < 2:
        return ""
    text = "\n### 📉 週別トレンド（直近）\n"
    text += "| 週 | 投稿数 | 合計インプ | 合計返信 |\n"
    text += "|-----|--------|-----------|--------|\n"
    for h in history[-8:]:  # 最新8週まで表示
        t = h["totals"]
        text += f"| {h['week']} | {t['posts']} | {t['views']:,} | {t['replies']} |\n"
    return text


def save_post_performance(records):
    existing = []
    if os.path.exists(POST_RECORDS_FILE):
        try:
            with open(POST_RECORDS_FILE) as f:
                existing = json.load(f)
        except (OSError, json.JSONDecodeError):
            existing = []
    merged = {item.get("id"): item for item in existing if item.get("id")}
    for item in records:
        if item.get("id"):
            merged[item["id"]] = item
    values = sorted(merged.values(), key=lambda item: item.get("timestamp", ""))[-1000:]
    with open(POST_RECORDS_FILE, "w") as f:
        json.dump(values, f, indent=2, ensure_ascii=False)
    return values


def parse_timestamp(timestamp):
    normalized = (timestamp or "").replace("Z", "+00:00")
    if re.search(r"[+-]\\d{4}$", normalized):
        normalized = normalized[:-5] + normalized[-5:-2] + ":" + normalized[-2:]
    try:
        return datetime.fromisoformat(normalized)
    except (TypeError, ValueError):
        return None


def is_recent(timestamp, days=7):
    try:
        value = parse_timestamp(timestamp)
        if value is None:
            return False
        return value >= now_jst.astimezone(timezone.utc) - timedelta(days=days)
    except TypeError:
        return False


# ── GitHub Issue ──────────────────────────────────────────────

def create_github_issue(title, body):
    if not GITHUB_TOKEN:
        print("GITHUB_TOKEN未設定のためIssueは作成されません")
        return
    res = requests.post(
        f"https://api.github.com/repos/{GITHUB_REPO}/issues",
        headers={
            "Authorization": f"Bearer {GITHUB_TOKEN}",
            "Accept": "application/vnd.github+json",
            "X-GitHub-Api-Version": "2022-11-28",
        },
        json={"title": title, "body": body}
    )
    result = res.json()
    if "html_url" in result:
        print(f"GitHub Issue作成: {result['html_url']}")
    else:
        print(f"Issue作成失敗: {result}")


# ── Main ──────────────────────────────────────────────────────

def main():
    print("=== 週次インサイトレポート開始 ===")

    # 1. 投稿とインサイトを取得
    print("投稿データを取得中...")
    posts = get_posts()
    if not posts:
        print("先週の投稿が見つかりませんでした")
        return

    fetched_results = []
    for post in posts:
        insights = get_insights(post["id"])
        published_at = parse_timestamp(post.get("timestamp", ""))
        age_hours = None
        if published_at:
            age_hours = round(
                (now_jst.astimezone(timezone.utc) - published_at.astimezone(timezone.utc)).total_seconds() / 3600,
                1,
            )
        fetched_results.append({
            "id": post["id"],
            "text": post.get("text", ""),
            "timestamp": post.get("timestamp", ""),
            "permalink": post.get("permalink", ""),
            "media_type": post.get("media_type", ""),
            "type": classify_post(post.get("text", "")),
            "views": insights.get("views", 0),
            "likes": insights.get("likes", 0),
            "replies": insights.get("replies", 0),
            "reposts": insights.get("reposts", 0),
            "quotes": insights.get("quotes", 0),
            "shares": insights.get("shares", 0),
            "age_hours": age_hours,
        })
        print(f"  {fmt(post.get('text',''), 25)} → 👁{insights.get('views',0)} 💬{insights.get('replies',0)}")

    all_records = save_post_performance(fetched_results)
    mature_records = [
        item for item in all_records
        if item.get("age_hours") is None or item.get("age_hours", 0) >= 24
    ]
    learning_profile = build_learning_profile(mature_records)
    learning_profile["generated_at"] = now_jst.isoformat()
    with open(LEARNING_PROFILE_FILE, "w") as f:
        json.dump(learning_profile, f, indent=2, ensure_ascii=False)
    learning_text = profile_as_prompt(learning_profile)
    results = [item for item in fetched_results if is_recent(item.get("timestamp", ""))]
    if not results:
        print("直近7日間の投稿がないため、取得できた最新データで分析します")
        results = fetched_results[:20]

    # 2. 集計
    total_views = sum(r["views"] for r in results)
    total_likes = sum(r["likes"] for r in results)
    total_replies = sum(r["replies"] for r in results)
    top_views = sorted(results, key=lambda x: x["views"], reverse=True)[:3]
    top_replies = sorted(results, key=lambda x: x["replies"], reverse=True)[:3]

    # タイプ別集計
    type_stats = {}
    for r in results:
        t = r["type"]
        if t not in type_stats:
            type_stats[t] = {"count": 0, "views": 0, "replies": 0}
        type_stats[t]["count"] += 1
        type_stats[t]["views"] += r["views"]
        type_stats[t]["replies"] += r["replies"]

    # 3. 今後の投稿を取得
    upcoming = get_upcoming_posts(14, start_offset=1)
    allowed_indices = {item["day_index"] for item in upcoming}

    # 4. Claude用テキスト生成
    performance_text = "### 投稿一覧（インプ順）\n"
    for i, r in enumerate(sorted(results, key=lambda x: x["views"], reverse=True), 1):
        performance_text += f"\n{i}. [{r['type']}] {fmt_ts(r['timestamp'])}\n"
        performance_text += f"   👁{r['views']} ❤️{r['likes']} 💬{r['replies']}\n"
        performance_text += f"   「{fmt(r['text'], 80)}」\n"

    performance_text += "\n### タイプ別平均\n"
    for t, s in sorted(type_stats.items(), key=lambda x: x[1]["views"] / max(x[1]["count"], 1), reverse=True):
        avg_views = s["views"] // max(s["count"], 1)
        avg_replies = s["replies"] / max(s["count"], 1)
        performance_text += f"- {t}（{s['count']}件）: 平均インプ {avg_views} / 平均返信 {avg_replies:.1f}\n"

    upcoming_text = ""
    for u in upcoming:
        upcoming_text += f"\n### day_index={u['day_index']} ({u['date']})\n"
        upcoming_text += f"【昼】{u['noon'][:120]}...\n" if len(u['noon']) > 120 else f"【昼】{u['noon']}\n"
        upcoming_text += f"【夜】{u['evening'][:120]}...\n" if len(u['evening']) > 120 else f"【夜】{u['evening']}\n"

    # 5. Google Trendsトレンド取得
    print("\nGoogle Trendsを取得中...")
    trends = get_google_trends()
    trends_text = format_trends_text(trends)
    if trends_text:
        print(f"  {len(trends)}キーワードのトレンドを取得しました")

    print("Threads内のトレンドシグナルを集計中...")
    threads_trends = get_threads_trend_signals()
    print(f"  集計キーワード: {len(threads_trends)}件")

    # 6. データ蓄積
    week_str = (now_jst - timedelta(days=7)).strftime("%m/%d") + "〜" + (now_jst - timedelta(days=1)).strftime("%m/%d")
    history = save_history(week_str, results, type_stats, "")  # analysis後に上書き

    # 7. Claude API呼び出し
    analysis = ""
    changed = []
    if ANTHROPIC_API_KEY and ENABLE_EXTERNAL_AI:
        print("\nClaude AIで分析中...")
        claude_response = call_claude(performance_text, upcoming_text, learning_text, trends_text)
        if claude_response:
            analysis, improvements = parse_claude_response(claude_response)
            print(f"改善提案: {len(improvements)}件")
            if improvements:
                print("posts_override.jsonを更新中...")
                changed = apply_improvements(improvements, allowed_indices)
    else:
        print("外部AI分析は無効です（ENABLE_EXTERNAL_AI=true で有効化）")

    # analysis確定後にhistoryを上書き保存
    if analysis:
        history = save_history(week_str, results, type_stats, analysis)

    # 7. レポート生成

    report = f"""## 📊 Sorane Threads 週次レポート（{week_str}）

### 合計
| 指標 | 数値 |
|------|------|
| 👁 インプレッション | {total_views:,} |
| ❤️ いいね | {total_likes:,} |
| 💬 返信 | {total_replies:,} |
| 📝 投稿数 | {len(results)} |

---

### 📈 タイプ別パフォーマンス
| タイプ | 件数 | 平均インプ | 平均返信 |
|--------|------|-----------|---------|
"""
    for t, s in sorted(type_stats.items(), key=lambda x: x[1]["views"] / max(x[1]["count"], 1), reverse=True):
        avg_v = s["views"] // max(s["count"], 1)
        avg_r = s["replies"] / max(s["count"], 1)
        report += f"| {t} | {s['count']} | {avg_v:,} | {avg_r:.1f} |\n"

    report += "\n---\n\n### 🏆 インプTOP3\n"
    for i, r in enumerate(top_views, 1):
        report += f"\n**{i}位** `{fmt_ts(r['timestamp'])}` [{r['type']}] 👁{r['views']:,} 💬{r['replies']}\n> {fmt(r['text'])}\n"

    report += "\n---\n\n### 💬 返信TOP3\n"
    for i, r in enumerate(top_replies, 1):
        report += f"\n**{i}位** `{fmt_ts(r['timestamp'])}` [{r['type']}] 💬{r['replies']} 👁{r['views']:,}\n> {fmt(r['text'])}\n"

    if trends_text:
        report += f"\n---\n\n{trends_text}"

    trend_text = build_trend_text(history)
    if trend_text:
        report += f"\n---\n{trend_text}"

    if analysis:
        report += f"\n---\n\n## 🤖 AI分析\n\n{analysis}"

    report += f"\n\n---\n\n## 🧠 累積学習\n\n- 学習済み投稿: {learning_profile['sample_size']}件\n"
    for stat in learning_profile.get("feature_stats", [])[:5]:
        report += f"- {stat['feature']}: 平均インプ {stat['avg_views']:,}（{stat['count']}件）\n"

    if threads_trends:
        report += "\n---\n\n## 🔥 Threads内トレンドシグナル\n"
        report += "個別投稿・ユーザー情報は保存せず、直近検索の件数だけを集計しています。\n\n"
        for item in threads_trends:
            report += f"- {item['keyword']}: 直近 {item['recent_count']}件\n"

    if changed:
        report += f"\n\n---\n\n## ✅ 自動更新された投稿（{len(changed)}件）\n"
        report += "以下の投稿がAI分析をもとに改善されました。\n\n"
        for c in changed:
            report += f"- day_index={c['day_index']} / {c['slot']}\n"
        report += "\n> sorane-appに反映するには「GitHubから取得」してください。\n"

    report += f"\n\n*生成: {now_jst.strftime('%Y-%m-%d %H:%M')} JST*"

    print("\n=== レポート生成完了 ===")
    create_github_issue(f"📊 週次レポート {week_str}", report)


if __name__ == "__main__":
    main()
