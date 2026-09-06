"""CLI entry point — fetch and display biometric data from connected devices."""

import json
from datetime import date, timedelta

from .auth import get_tokens
from .connectors.oura import OuraClient
from .connectors.whoop import WhoopClient


def fetch_all(days: int = 7):
    start = date.today() - timedelta(days=days)
    end = date.today()
    results = {"sleep": [], "recovery": [], "activity": []}

    if get_tokens("whoop"):
        print("Fetching Whoop data...")
        whoop = WhoopClient()
        try:
            results["sleep"].extend([r.model_dump(mode="json") for r in whoop.get_sleep(start, end)])
            results["recovery"].extend([r.model_dump(mode="json") for r in whoop.get_recovery(start, end)])
            results["activity"].extend([r.model_dump(mode="json") for r in whoop.get_workouts(start, end)])
        finally:
            whoop.close()
    else:
        print("Whoop: not connected (run python -m src.auth)")

    if get_tokens("oura"):
        print("Fetching Oura data...")
        oura = OuraClient()
        try:
            results["sleep"].extend([r.model_dump(mode="json") for r in oura.get_sleep(start, end)])
            results["recovery"].extend([r.model_dump(mode="json") for r in oura.get_readiness(start, end)])
            results["activity"].extend([r.model_dump(mode="json") for r in oura.get_activity(start, end)])
        finally:
            oura.close()
    else:
        print("Oura: not connected (run python -m src.auth)")

    return results


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="Fetch biometric data from Whoop & Oura")
    parser.add_argument("--days", type=int, default=7, help="Number of days to fetch (default: 7)")
    parser.add_argument("--json", action="store_true", help="Output as JSON")
    args = parser.parse_args()

    data = fetch_all(args.days)

    if args.json:
        print(json.dumps(data, indent=2, default=str))
    else:
        for category, records in data.items():
            print(f"\n{'='*40}")
            print(f" {category.upper()} ({len(records)} records)")
            print(f"{'='*40}")
            for r in records:
                src = r["source"]
                dt = r["date"]
                if category == "sleep":
                    hrs = r["total_sleep_seconds"] / 3600
                    score = r.get("score") or "—"
                    print(f"  [{src}] {dt}  {hrs:.1f}h sleep  score: {score}")
                elif category == "recovery":
                    score = r.get("score") or "—"
                    hrv = r.get("hrv_ms") or "—"
                    rhr = r.get("resting_hr") or "—"
                    print(f"  [{src}] {dt}  score: {score}  HRV: {hrv}  RHR: {rhr}")
                elif category == "activity":
                    atype = r.get("activity_type") or "—"
                    cal = r.get("calories")
                    cal_str = f"{cal:.0f} cal" if cal else "—"
                    print(f"  [{src}] {dt}  {atype}  {cal_str}")
