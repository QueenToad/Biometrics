"""CLI — fetch biometric data, show it, and sync it into Notion."""

import json
from datetime import date, timedelta
from typing import List

from .aggregate import build_daily
from .auth import get_tokens
from .connectors.oura import OuraClient
from .connectors.whoop import WhoopClient
from .models.activity import ActivityRecord
from .models.daily import DailyRecord
from .models.recovery import RecoveryRecord
from .models.sleep import SleepRecord


def fetch_all(days: int = 7):
    start = date.today() - timedelta(days=days)
    end = date.today()
    sleep: List[SleepRecord] = []
    recovery: List[RecoveryRecord] = []
    activity: List[ActivityRecord] = []

    if get_tokens("whoop"):
        print("Fetching Whoop data...")
        whoop = WhoopClient()
        try:
            sleep += whoop.get_sleep(start, end)
            recovery += whoop.get_recovery(start, end)
            activity += whoop.get_workouts(start, end)
        finally:
            whoop.close()
    else:
        print("Whoop: not connected (run python -m src.auth)")

    if get_tokens("oura"):
        print("Fetching Oura data...")
        oura = OuraClient()
        try:
            sleep += oura.get_sleep(start, end)
            recovery += oura.get_readiness(start, end)
            activity += oura.get_activity(start, end)
        finally:
            oura.close()
    else:
        print("Oura: not connected (run python -m src.auth)")

    return sleep, recovery, activity


def print_daily(rows: List[DailyRecord]) -> None:
    if not rows:
        print("\nNo data for this range.")
        return
    header = (f"{'День':<12}{'источник':<9}{'Отбой':>7}{'Подъём':>8}{'Сон':>7}"
              f"{'Score':>7}{'Recov':>7}{'HRV':>7}{'RHR':>6}  Тренировки")
    print("\n" + header)
    print("-" * len(header))
    last_day = None
    for r in rows:
        if last_day and r.day != last_day:
            print()
        last_day = r.day
        nap = " 💤" if r.had_nap else ""
        print(
            f"{r.day:<12}{r.source:<9}"
            f"{r.bedtime or '—':>7}"
            f"{r.wake_time or '—':>8}"
            f"{(str(r.sleep_hours) + 'ч') if r.sleep_hours else '—':>7}"
            f"{r.sleep_score if r.sleep_score is not None else '—':>7}"
            f"{r.recovery_score if r.recovery_score is not None else '—':>7}"
            f"{r.hrv_ms if r.hrv_ms is not None else '—':>7}"
            f"{int(r.resting_hr) if r.resting_hr is not None else '—':>6}"
            f"  {r.workouts or ''}{nap}"
        )


def main():
    import argparse

    parser = argparse.ArgumentParser(description="Whoop & Oura biometrics")
    parser.add_argument("--days", type=int, default=7, help="days to fetch (default: 7)")
    parser.add_argument("--json", action="store_true", help="print raw JSON")
    parser.add_argument("--sync", action="store_true", help="write the days into Notion")
    args = parser.parse_args()

    sleep, recovery, activity = fetch_all(args.days)
    rows = build_daily(sleep, recovery, activity)

    if args.json:
        print(json.dumps([r.model_dump(mode="json") for r in rows], indent=2, ensure_ascii=False))
    else:
        print_daily(rows)

    if args.sync:
        from .connectors.notion import NotionClient

        print("\nSyncing to Notion...")
        notion = NotionClient()
        try:
            counts = notion.upsert_all(rows)
        finally:
            notion.close()
        print(f"Notion: {counts['created']} created, {counts['updated']} updated")


if __name__ == "__main__":
    main()
