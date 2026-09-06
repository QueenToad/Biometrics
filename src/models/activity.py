from datetime import datetime
from typing import Optional

from pydantic import BaseModel


class ActivityRecord(BaseModel):
    source: str  # "whoop" or "oura"
    date: str
    activity_type: Optional[str] = None
    start_time: Optional[datetime] = None
    end_time: Optional[datetime] = None
    duration_seconds: Optional[int] = None
    calories: Optional[float] = None
    avg_hr: Optional[float] = None
    max_hr: Optional[float] = None
    strain: Optional[float] = None  # whoop-specific
    steps: Optional[int] = None  # oura-specific
    distance_meters: Optional[float] = None
