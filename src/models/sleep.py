from datetime import datetime
from typing import Optional

from pydantic import BaseModel


class SleepStage(BaseModel):
    stage: str  # awake, light, deep, rem
    start: datetime
    end: datetime
    duration_seconds: int


class SleepRecord(BaseModel):
    source: str  # "whoop" or "oura"
    date: str
    total_sleep_seconds: int
    rem_seconds: Optional[int] = None
    deep_seconds: Optional[int] = None
    light_seconds: Optional[int] = None
    awake_seconds: Optional[int] = None
    efficiency: Optional[float] = None
    score: Optional[int] = None
    heart_rate_avg: Optional[float] = None
    hrv_avg: Optional[float] = None
    respiratory_rate_avg: Optional[float] = None
    # Local wall-clock times, not UTC — bedtime only means anything locally.
    start_time: Optional[datetime] = None
    end_time: Optional[datetime] = None
    is_nap: bool = False
