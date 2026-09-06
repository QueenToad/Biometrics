from datetime import datetime

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
    rem_seconds: int | None = None
    deep_seconds: int | None = None
    light_seconds: int | None = None
    awake_seconds: int | None = None
    efficiency: float | None = None
    score: int | None = None
    heart_rate_avg: float | None = None
    hrv_avg: float | None = None
    respiratory_rate_avg: float | None = None
    start_time: datetime | None = None
    end_time: datetime | None = None
