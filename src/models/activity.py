from datetime import datetime

from pydantic import BaseModel


class ActivityRecord(BaseModel):
    source: str  # "whoop" or "oura"
    date: str
    activity_type: str | None = None
    start_time: datetime | None = None
    end_time: datetime | None = None
    duration_seconds: int | None = None
    calories: float | None = None
    avg_hr: float | None = None
    max_hr: float | None = None
    strain: float | None = None  # whoop-specific
    steps: int | None = None  # oura-specific
    distance_meters: float | None = None
