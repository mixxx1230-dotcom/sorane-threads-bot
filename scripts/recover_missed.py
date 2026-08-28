"""12:17/18:07の予定投稿が欠けた場合だけ復旧する。"""
import json
import os
import subprocess
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

JST = timezone(timedelta(hours=9))
ROOT = Path(__file__).resolve().parent.parent
HISTORY_FILE = ROOT / "data" / "post_history.json"
SCHEDULE = {"noon": (12, 17), "evening": (18, 7)}
GRACE_MINUTES = 23
AUTOMATION_START_DATE = os.environ.get("AUTOMATION_START_DATE", "2026-08-29")


def load_history():
    if not HISTORY_FILE.exists():
        return {}
    try:
        return json.loads(HISTORY_FILE.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return {}


def due_targets(now):
    if str(now.date()) < AUTOMATION_START_DATE:
        return
    history = load_history()
    # 当日分だけを見る。翌日に前日分を誤投稿しない。
    for days_ago in (0,):
        target = (now - timedelta(days=days_ago)).date()
        for slot, (hour, minute) in SCHEDULE.items():
            scheduled = datetime.combine(target, datetime.min.time(), JST).replace(
                hour=hour, minute=minute
            )
            if now < scheduled + timedelta(minutes=GRACE_MINUTES):
                continue
            key = f"{target}_{slot}"
            if key not in history:
                yield target, slot


def main():
    now = datetime.now(JST)
    targets = list(due_targets(now))
    if not targets:
        print("復旧対象なし")
        return 0

    for target, slot in targets:
        print(f"未投稿を復旧: {target}_{slot}")
        env = os.environ.copy()
        env["TARGET_DATE"] = str(target)
        env["SLOT"] = slot
        subprocess.run(
            [sys.executable, str(ROOT / "scripts" / "post_scheduled.py")],
            check=True,
            env=env,
            cwd=ROOT / "scripts",
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
