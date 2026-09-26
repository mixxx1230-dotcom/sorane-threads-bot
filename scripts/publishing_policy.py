"""期間限定の配信ポリシー判定。期間終了後は自動的に通常運用へ戻る。"""

import json
from datetime import date
from pathlib import Path

POLICY_FILE = Path(__file__).resolve().parent.parent / "data" / "publishing_policy.json"


def load_policy():
    try:
        return json.loads(POLICY_FILE.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}


def is_active(policy, target_date):
    try:
        return date.fromisoformat(policy["active_from"]) <= target_date <= date.fromisoformat(policy["active_until"])
    except (KeyError, TypeError, ValueError):
        return False


def should_publish(slot, target_date, force=False):
    if force:
        return True, "forced"
    policy = load_policy()
    if not is_active(policy, target_date):
        return True, "standard"
    if slot == "blog" and not policy.get("blog_enabled", True):
        return False, policy.get("reason", "blog paused")
    if slot not in policy.get("allowed_slots", []):
        return False, policy.get("reason", "slot paused")
    if target_date.weekday() in policy.get("skip_weekdays", []):
        return False, policy.get("reason", "weekday paused")
    return True, policy.get("reason", "reset test")
