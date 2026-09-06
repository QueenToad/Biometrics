"""Collapse raw records into one summary per device per day."""

from collections import Counter, defaultdict
from typing import Dict, List, Optional, Tuple

from .models.activity import ActivityRecord
from .models.daily import DailyRecord
from .models.recovery import RecoveryRecord
from .models.sleep import SleepRecord

# Oura's daily_activity is a whole-day rollup, not a session. It carries the
# day's calories but does not belong in a list of workouts.
DAILY_ROLLUP = "daily"


def _hours(seconds: Optional[int]) -> Optional[float]:
    return round(seconds / 3600, 1) if seconds else None


def _summarize_workouts(items: List[ActivityRecord]) -> Optional[str]:
    """'walking ×4, hiking-rucking, pilates' — ordered by how often it appears."""
    names = [i.activity_type for i in items
             if i.activity_type and i.activity_type != DAILY_ROLLUP]
    if not names:
        return None
    counts = Counter(names)
    return ", ".join(f"{n} ×{c}" if c > 1 else n for n, c in counts.most_common())


def build_daily(
    sleep: List[SleepRecord],
    recovery: List[RecoveryRecord],
    activity: List[ActivityRecord],
) -> List[DailyRecord]:
    """One DailyRecord per (day, device).

    The two devices are kept apart rather than merged: they measure
    differently, and picking a winner per field would hide that.
    """
    buckets: Dict[Tuple[str, str], dict] = defaultdict(
        lambda: {"sleep": [], "recovery": [], "activity": []}
    )

    for kind, records in (("sleep", sleep), ("recovery", recovery), ("activity", activity)):
        for r in records:
            if r.date:
                buckets[(r.date, r.source)][kind].append(r)

    rows = []
    for (day, source) in sorted(buckets):
        bucket = buckets[(day, source)]
        nights = [s for s in bucket["sleep"] if not s.is_nap]
        naps = [s for s in bucket["sleep"] if s.is_nap]

        # More than one night record for a day is unusual; take the longest so
        # a fragment doesn't outrank the real night.
        night = max(nights, key=lambda s: s.total_sleep_seconds, default=None)
        rec = bucket["recovery"][0] if bucket["recovery"] else None
        acts = bucket["activity"]
        calories = sum(a.calories for a in acts if a.calories)

        rows.append(DailyRecord(
            day=day,
            source=source,
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
        ))
    return rows
