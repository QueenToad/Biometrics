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
    header = f"{'День':<12}{'Отбой':>7}{'Подъём':>8}{'Сон':>7}{'Score':>7}{'Recov':>7}{'HRV':>7}{'RHR':>6}  Тренировки"
    print("\n" + header)
    print("-" * len(header))
    for r in rows:
        nap = " 💤" if r.had_nap else ""
        print(
            f"{r.day:<12}"
            f"{r.bedtime or '—':>7}"
            f"{r.wake_time or '—':>8}"
            f"{(str(r.sleep_hours) + 'ч') if r.sleep_hours else '—':>7}"
            f"{r.sleep_score if r.sleep_score is not None else '—':>7}"
            f"{r.recovery_score if r.recovery_score is not None else '—':>7}"
            f"{r.hrv_ms if r.hrv_ms is not None else '—':>7}"
            f"{int(r.resting_hr) if r.resting_hr is not None else '—':>6}"
            f"  {r.workouts or ''}{nap}"
        )


def print_comparison(sleep: List[SleepRecord], recovery: List[RecoveryRecord]) -> None:
    """Show each provider's own numbers side by side for the same night."""
    days = sorted({r.date for r in sleep + recovery if r.date})
    header = (f"{'День':<12}{'источник':<9}{'Отбой':>7}{'Подъём':>8}{'Сон':>7}"
              f"{'Score':>7}{'Recov':>7}{'HRV':>7}{'RHR':>6}")
    print("\n" + header)
    print("-" * len(header))
    for day in days:
        for source in ("whoop", "oura"):
            night = next((s for s in sleep
                          if s.date == day and s.source == source and not s.is_nap), None)
            rec = next((r for r in recovery if r.date == day and r.source == source), None)
            if not night and not rec:
                continue
            hours = round(night.total_sleep_seconds / 3600, 1) if night else None
            print(
                f"{day:<12}{source:<9}"
                f"{(night.start_time.strftime('%H:%M') if night and night.start_time else '—'):>7}"
                f"{(night.end_time.strftime('%H:%M') if night and night.end_time else '—'):>8}"
                f"{(str(hours) + 'ч') if hours else '—':>7}"
                f"{(night.score if night and night.score is not None else '—'):>7}"
                f"{(rec.score if rec and rec.score is not None else '—'):>7}"
                f"{(round(rec.hrv_ms, 1) if rec and rec.hrv_ms else '—'):>7}"
                f"{(int(rec.resting_hr) if rec and rec.resting_hr else '—'):>6}"
            )
        print()


def main():
    import argparse

    parser = argparse.ArgumentParser(description="Whoop & Oura biometrics")
    parser.add_argument("--days", type=int, default=7, help="days to fetch (default: 7)")
    parser.add_argument("--json", action="store_true", help="print raw JSON")
    parser.add_argument("--sync", action="store_true", help="write the days into Notion")
    parser.add_argument("--compare", action="store_true",
                        help="show each provider's numbers instead of the merged row")
    args = parser.parse_args()

    sleep, recovery, activity = fetch_all(args.days)

    if args.compare:
        print_comparison(sleep, recovery)
        return

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
