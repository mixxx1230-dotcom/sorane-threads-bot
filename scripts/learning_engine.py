"""投稿実績から再利用可能な学習プロファイルを作る純粋関数群。"""

from collections import defaultdict
from datetime import datetime, timedelta, timezone
import math
import re


def engagement_score(metrics):
    """規模が違う投稿同士を比較しやすい複合スコア。"""
    views = max(int(metrics.get("views", 0) or 0), 0)
    likes = max(int(metrics.get("likes", 0) or 0), 0)
    replies = max(int(metrics.get("replies", 0) or 0), 0)
    reposts = max(int(metrics.get("reposts", 0) or 0), 0)
    quotes = max(int(metrics.get("quotes", 0) or 0), 0)
    interactions = likes + replies * 3 + reposts * 4 + quotes * 5
    return round(math.log1p(views) * 10 + interactions / max(views, 1) * 1000, 2)


JST = timezone(timedelta(hours=9))


def _opening_type(first_line):
    if any(mark in first_line for mark in ("①", "②", "③", "④", "どっち", "何番")):
        return "choice"
    if any(word in first_line for word in ("施術して", "お客様", "最近多い")):
        return "practitioner_observation"
    if re.search(r"[？?]|ませんか|ますか", first_line):
        return "question"
    if any(word in first_line for word in ("実は", "意外", "原因", "じゃない")):
        return "surprising_fact"
    return "statement"


def _topic(text):
    groups = (
        ("availability", ("空き状況", "ご案内可能")),
        ("blog", ("ブログを更新", "ぜひご覧")),
        ("local_conversation", ("おすすめのご飯", "心斎橋駅", "四ツ橋駅")),
        ("recruitment", ("撮影協力", "モデル", "DMください")),
        ("eye_strain", ("眼精疲労", "目の疲れ", "目の奥")),
        ("sleep", ("睡眠", "寝ても", "寝る前", "休めた気")),
        ("jaw_clenching", ("食いしば", "奥歯", "上下の歯")),
        ("neck_shoulder", ("首肩", "肩こり", "首の付け根", "肩が")),
    )
    for name, words in groups:
        if any(word in text for word in words):
            return name
    return "other"


def extract_features(text, timestamp="", media_type=""):
    text = text or ""
    first_line = next((line.strip() for line in text.splitlines() if line.strip()), "")
    hour = None
    weekday = None
    if timestamp:
        try:
            normalized = timestamp.replace("Z", "+00:00")
            if re.search(r"[+-]\d{4}$", normalized):
                normalized = normalized[:-5] + normalized[-5:-2] + ":" + normalized[-2:]
            parsed = datetime.fromisoformat(normalized)
            if parsed.tzinfo is None:
                parsed = parsed.replace(tzinfo=timezone.utc)
            parsed = parsed.astimezone(JST)
            hour = parsed.hour
            weekday = parsed.weekday()
        except ValueError:
            pass
    return {
        "length_band": "short" if len(text) < 120 else ("medium" if len(text) < 240 else "long"),
        "hook_question": bool(re.search(r"[？?]|ませんか|ますか", first_line)),
        "has_numbered_choices": any(mark in text for mark in ("①", "②", "③", "④")),
        "has_selfcare": any(word in text for word in ("てみて", "秒", "呼吸", "ほぐ", "ストレッチ")),
        "has_local_cta": "心斎橋" in text,
        "has_booking_link": "http" in text or "予約はこちら" in text,
        "opening_type": _opening_type(first_line),
        "topic": _topic(text),
        "media": "image_or_video" if media_type in ("IMAGE", "VIDEO", "CAROUSEL_ALBUM") else "text",
        "emoji_band": "none" if not re.search(r"[^\w\s、。！？!?（）()「」『』・〜ー]", text) else "present",
        "hour": hour,
        "time_band": None if hour is None else ("morning" if hour < 11 else ("noon" if hour < 17 else "evening")),
        "weekday": weekday,
    }


def build_learning_profile(records):
    """全履歴を集約し、特徴別の平均値と上位投稿を返す。"""
    enriched = []
    buckets = defaultdict(lambda: {"count": 0, "views": 0, "score": 0.0})
    for record in records:
        item = dict(record)
        item["features"] = extract_features(
            item.get("text", ""), item.get("timestamp", ""), item.get("media_type", "")
        )
        item["score"] = engagement_score(item)
        enriched.append(item)
        for name, value in item["features"].items():
            if value is None:
                continue
            if isinstance(value, bool):
                value = str(value).lower()
            key = f"{name}:{value}"
            buckets[key]["count"] += 1
            buckets[key]["views"] += int(item.get("views", 0) or 0)
            buckets[key]["score"] += item["score"]

    all_views = sorted(int(item.get("views", 0) or 0) for item in enriched)
    median_views = all_views[len(all_views) // 2] if all_views else 0
    feature_stats = []
    for key, values in buckets.items():
        count = values["count"]
        if count < 2:
            continue
        feature_stats.append({
            "feature": key,
            "count": count,
            "avg_views": round(values["views"] / count),
            "avg_score": round(values["score"] / count, 2),
            "view_lift": round((values["views"] / count) / max(median_views, 1), 2),
        })
    feature_stats.sort(key=lambda item: item["avg_score"], reverse=True)
    enriched.sort(key=lambda item: item["score"], reverse=True)
    return {
        "sample_size": len(enriched),
        "median_views": median_views,
        "feature_stats": feature_stats,
        "top_posts": enriched[:10],
    }


def profile_as_prompt(profile):
    if not profile.get("sample_size"):
        return "学習サンプルはまだありません。推測を断定せず、検証可能な案を作ること。"
    lines = [f"累計学習投稿数: {profile['sample_size']}", "特徴別パフォーマンス上位:"]
    for stat in profile.get("feature_stats", [])[:12]:
        lines.append(
            f"- {stat['feature']}（{stat['count']}件）: 平均インプ {stat['avg_views']} / "
            f"中央値比 {stat.get('view_lift', 0)}倍 / 複合スコア {stat['avg_score']}"
        )
    lines.append("上位投稿:")
    for post in profile.get("top_posts", [])[:5]:
        text = (post.get("text") or "").replace("\n", " ")[:90]
        lines.append(f"- score={post['score']} views={post.get('views', 0)}: {text}")
    return "\n".join(lines)

