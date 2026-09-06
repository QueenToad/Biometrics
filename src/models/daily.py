"""One row per day: what the morning check-in actually needs to see."""

from typing import Optional

from pydantic import BaseModel


class DailyRecord(BaseModel):
    day: str  # YYYY-MM-DD, the day you woke up
    source: str  # "whoop" or "oura" — one row per device per day
    bedtime: Optional[str] = None  # local HH:MM
    wake_time: Optional[str] = None  # local HH:MM
    sleep_hours: Optional[float] = None
    sleep_score: Optional[int] = None
    recovery_score: Optional[int] = None
    hrv_ms: Optional[float] = None
    resting_hr: Optional[float] = None
    rem_hours: Optional[float] = None
    deep_hours: Optional[float] = None
    had_nap: bool = False
    activity_calories: Optional[int] = None
    workouts: Optional[str] = None
