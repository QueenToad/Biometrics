"""Collapse per-provider records into one row per day."""

from collections import Counter, defaultdict
from typing import Dict, List, Optional

from .models.activity import ActivityRecord
from .models.daily import DailyRecord
from .models.recovery import RecoveryRecord
from .models.sleep import SleepRecord


def _hours(seconds: Optional[int]) -> Optional[float]:
    return round(seconds / 3600, 1) if seconds else None


def _summarize_workouts(items: List[ActivityRecord]) -> Optional[str]:
    """'walking ×4, hiking-rucking, pilates' — ordered by how often it appears."""
    names = [i.activity_type for i in items if i.activity_type]
    if not names:
        return None
    counts = Counter(names)
    parts = [f"{name} ×{n}" if n > 1 else name for name, n in counts.most_common()]
    return ", ".join(parts)


def build_daily(
    sleep: List[SleepRecord],
    recovery: List[RecoveryRecord],
    activity: List[ActivityRecord],
) -> List[DailyRecord]:
    by_day: Dict[str, dict] = defaultdict(lambda: {"sleep": [], "recovery": [], "activity": []})

    for r in sleep:
        if r.date:
            by_day[r.date]["sleep"].append(r)
    for r in recovery:
        if r.date:
            by_day[r.date]["recovery"].append(r)
    for r in activity:
        if r.date:
            by_day[r.date]["activity"].append(r)

    rows = []
    for day in sorted(by_day):
        bucket = by_day[day]
        nights = [s for s in bucket["sleep"] if not s.is_nap]
        naps = [s for s in bucket["sleep"] if s.is_nap]

        # A day can hold more than one night record only in odd cases; take the
        # longest as the night's sleep so a fragment doesn't outrank it.
        night = max(nights, key=lambda s: s.total_sleep_seconds, default=None)
        rec = bucket["recovery"][0] if bucket["recovery"] else None
        acts = bucket["activity"]

        calories = sum(a.calories for a in acts if a.calories)
        sources = sorted({r.source for r in bucket["sleep"] + bucket["recovery"] + acts})

        rows.append(DailyRecord(
            day=day,
            bedtime=night.start_time.strftime("%H:%M") if night and night.start_time else None,
            wake_time=night.end_time.strftime("%H:%M") if night and night.end_time else None,
            sleep_hours=_hours(night.total_sleep_seconds) if night else None,
            sleep_score=night.score if night else None,
            recovery_score=rec.score if rec else None,
            hrv_ms=round(rec.hrv_ms, 1) if rec and rec.hrv_ms else None,
            resting_hr=rec.resting_hr if rec else None,
            rem_hours=_hours(night.rem_seconds) if night else None,
            deep_hours=_hours(night.deep_seconds) if night else None,
            had_nap=bool(naps),
            activity_calories=round(calories) if calories else None,
            workouts=_summarize_workouts(acts),
            sources="+".join(sources) if sources else None,
        ))
    return rows
