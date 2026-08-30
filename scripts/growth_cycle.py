"""Soraneの実績を保存し、未投稿文の到達予測とA/B比較を作る。外部AIへは送信しない。"""

import json
import os
from datetime import date, datetime, timedelta, timezone

import requests

from learning_engine import build_learning_profile, extract_features

JST = timezone(timedelta(hours=9))
ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
PERFORMANCE_FILE = os.path.join(ROOT, "data", "post_performance.json")
PROFILE_FILE = os.path.join(ROOT, "data", "learning_profile.json")
FORECAST_FILE = os.path.join(ROOT, "data", "growth_forecasts.json")
OVERRIDE_FILE = os.path.join(ROOT, "data", "posts_override.json")
START_DATE = date.fromisoformat(os.environ.get("START_DATE", "2026-08-19"))
TOKEN = os.environ.get("THREADS_ACCESS_TOKEN", "").strip()
USER_ID = os.environ.get("THREADS_USER_ID", "").strip()


def load_json(path, fallback):
    try:
        with open(path, encoding="utf-8") as handle:
            return json.load(handle)
    except (OSError, json.JSONDecodeError):
        return fallback


def save_json(path, value):
    with open(path, "w", encoding="utf-8") as handle:
        json.dump(value, handle, ensure_ascii=False, indent=2)


def fetch_posts():
    response = requests.get(
        f"https://graph.threads.net/v1.0/{USER_ID}/threads",
        params={
            "fields": "id,text,timestamp,media_type,permalink",
            "limit": 100,
            "access_token": TOKEN,
        },
        timeout=30,
    )
    response.raise_for_status()
    return [item for item in response.json().get("data", []) if item.get("media_type") != "REPOST_FACADE"]


def fetch_insights(post_id):
    response = requests.get(
        f"https://graph.threads.net/v1.0/{post_id}/insights",
        params={"metric": "views,likes,replies,reposts,quotes,shares", "access_token": TOKEN},
        timeout=30,
    )
    response.raise_for_status()
    values = {}
    for metric in response.json().get("data", []):
        values[metric.get("name")] = metric.get("values", [{}])[0].get("value", 0)
    return values


def classify_variant(features):
    if features.get("has_numbered_choices"):
        return "A_choice"
    opening = features.get("opening_type")
    if opening == "practitioner_observation":
        return "B_practitioner"
    if opening == "question":
        return "C_question"
    return "D_statement"


def suggestions(features):
    result = []
    if features.get("opening_type") == "statement":
        result.append("冒頭を質問・施術者の発見・4択のいずれかにする")
    if not features.get("has_numbered_choices") and not features.get("hook_question"):
        result.append("読者が返信できる余白を1つ加える")
    if features.get("has_booking_link"):
        result.append("拡散枠では予約誘導を外し、会話を優先する")
    if features.get("length_band") == "long":
        result.append("要点を1つに絞り、260文字程度まで短くする")
    return result[:3]


def forecast(profile, text, timestamp, media_type="TEXT_POST"):
    features = extract_features(text, timestamp, media_type)
    stats = {item["feature"]: item for item in profile.get("feature_stats", [])}
    lifts = []
    for name in ("opening_type", "topic", "has_numbered_choices", "has_booking_link", "time_band", "length_band", "media"):
        value = features.get(name)
        if isinstance(value, bool):
            value = str(value).lower()
        item = stats.get(f"{name}:{value}")
        if item and item.get("count", 0) >= 2:
            lifts.append(max(0.5, min(float(item.get("view_lift", 1)), 2.0)))
    lift = sum(lifts) / len(lifts) if lifts else 1.0
    baseline = max(int(profile.get("median_views", 100) or 100), 1)
    midpoint = round(baseline * lift)
    return {
        "predicted_views": {"low": round(midpoint * 0.7), "high": round(midpoint * 1.4)},
        "baseline_views": baseline,
        "relative_reach": round(lift, 2),
        "variant": classify_variant(features),
        "suggestions": suggestions(features),
        "features": features,
    }


def main():
    if not TOKEN or not USER_ID:
        raise SystemExit("THREADS_ACCESS_TOKEN / THREADS_USER_ID が未設定です")
    now = datetime.now(JST)
    existing = {item.get("id"): item for item in load_json(PERFORMANCE_FILE, []) if item.get("id")}
    for post in fetch_posts():
        metrics = fetch_insights(post["id"])
        record = existing.get(post["id"], {})
        snapshots = record.get("snapshots", [])
        current = {"captured_at": now.isoformat(), **metrics}
        comparable = {key: value for key, value in current.items() if key != "captured_at"}
        previous = {key: value for key, value in (snapshots[-1] if snapshots else {}).items() if key != "captured_at"}
        if not snapshots or comparable != previous:
            snapshots.append(current)
        existing[post["id"]] = {**post, **metrics, "snapshots": snapshots[-20:]}
    records = sorted(existing.values(), key=lambda item: item.get("timestamp", ""))[-100:]
    save_json(PERFORMANCE_FILE, records)
    mature_records = []
    for item in records:
        try:
            published = datetime.fromisoformat(item.get("timestamp", "").replace("Z", "+00:00"))
            if published.tzinfo is None:
                published = published.replace(tzinfo=timezone.utc)
            if now.astimezone(timezone.utc) - published.astimezone(timezone.utc) >= timedelta(hours=24):
                mature_records.append(item)
        except (TypeError, ValueError):
            mature_records.append(item)
    profile = build_learning_profile(mature_records)
    profile["generated_at"] = now.isoformat()
    save_json(PROFILE_FILE, profile)

    overrides = load_json(OVERRIDE_FILE, [])
    forecasts = []
    for offset in range(1, 15):
        target = now.date() + timedelta(days=offset)
        index = (target - START_DATE).days % len(overrides)
        for slot, hour in (("noon", 12), ("evening", 18)):
            post = overrides[index].get(slot, {})
            text = post.get("text", "")
            timestamp = datetime.combine(target, datetime.min.time(), JST).replace(hour=hour).isoformat()
            forecasts.append({
                "date": str(target), "day_index": index, "slot": slot,
                "text": text, **forecast(profile, text, timestamp),
            })
    variant_results = {}
    for record in records:
        variant = classify_variant(extract_features(record.get("text", ""), record.get("timestamp", ""), record.get("media_type", "")))
        bucket = variant_results.setdefault(variant, {"posts": 0, "views": 0, "replies": 0, "reposts": 0})
        bucket["posts"] += 1
        for metric in ("views", "replies", "reposts"):
            bucket[metric] += int(record.get(metric, 0) or 0)
    for bucket in variant_results.values():
        bucket["avg_views"] = round(bucket["views"] / max(bucket["posts"], 1))
    save_json(FORECAST_FILE, {
        "generated_at": now.isoformat(),
        "baseline_views": profile.get("median_views", 0),
        "variant_results": variant_results,
        "forecasts": forecasts,
    })
    print(f"分析完了: 実績{len(records)}件 / 予測{len(forecasts)}件")


if __name__ == "__main__":
    main()
