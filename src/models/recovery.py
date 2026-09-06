from typing import Optional

from pydantic import BaseModel


class RecoveryRecord(BaseModel):
    source: str  # "whoop" or "oura"
    date: str
    score: Optional[int] = None
    hrv_ms: Optional[float] = None
    resting_hr: Optional[float] = None
    spo2: Optional[float] = None
    skin_temp_celsius: Optional[float] = None
    body_battery: Optional[int] = None
