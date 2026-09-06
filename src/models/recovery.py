from pydantic import BaseModel


class RecoveryRecord(BaseModel):
    source: str  # "whoop" or "oura"
    date: str
    score: int | None = None
    hrv_ms: float | None = None
    resting_hr: float | None = None
    spo2: float | None = None
    skin_temp_celsius: float | None = None
    body_battery: int | None = None
