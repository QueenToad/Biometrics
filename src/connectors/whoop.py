"""Whoop API client — https://developer.whoop.com/api"""

from datetime import date, timedelta
from typing import List, Optional

import httpx

from ..auth import get_tokens, refresh_token, save_provider_tokens
from ..config import Settings
from ..models.activity import ActivityRecord
from ..models.recovery import RecoveryRecord
from ..models.sleep import SleepRecord

PROVIDER = "whoop"


class WhoopClient:
    def __init__(self, settings: Optional[Settings] = None):
        self.settings = settings or Settings()
        self.base = self.settings.whoop.api_base
        self._client: Optional[httpx.Client] = None

    def _get_client(self) -> httpx.Client:
        if self._client:
            return self._client

        tokens = get_tokens(PROVIDER)
        if not tokens:
            raise RuntimeError("Whoop not authorized. Run: python -m src.auth")

        self._client = httpx.Client(
            base_url=self.base,
            headers={"Authorization": f"Bearer {tokens['access_token']}"},
            timeout=30,
        )
        return self._client

    def _request(self, method: str, path: str, **kwargs) -> dict:
        client = self._get_client()
        resp = client.request(method, path, **kwargs)

        if resp.status_code == 401:
            tokens = get_tokens(PROVIDER)
            if tokens and "refresh_token" in tokens:
                new_tokens = refresh_token(PROVIDER, tokens["refresh_token"], self.settings)
                save_provider_tokens(PROVIDER, new_tokens)
                client.headers["Authorization"] = f"Bearer {new_tokens['access_token']}"
                resp = client.request(method, path, **kwargs)

        resp.raise_for_status()
        return resp.json()

    def get_sleep(self, start: Optional[date] = None, end: Optional[date] = None) -> List[SleepRecord]:
        start = start or date.today() - timedelta(days=7)
        end = end or date.today()
        data = self._request("GET", "/v1/activity/sleep", params={
            "start": start.isoformat(),
            "end": end.isoformat(),
        })
        records = []
        for item in data.get("records", []):
            score = item.get("score", {})
            records.append(SleepRecord(
                source=PROVIDER,
                date=item.get("during", {}).get("lower", "")[:10],
                total_sleep_seconds=score.get("stage_summary", {}).get("total_in_bed_time_milli", 0) // 1000,
                rem_seconds=score.get("stage_summary", {}).get("total_rem_sleep_time_milli", 0) // 1000,
                deep_seconds=score.get("stage_summary", {}).get("total_slow_wave_sleep_time_milli", 0) // 1000,
                light_seconds=score.get("stage_summary", {}).get("total_light_sleep_time_milli", 0) // 1000,
                awake_seconds=score.get("stage_summary", {}).get("total_awake_time_milli", 0) // 1000,
                efficiency=score.get("sleep_efficiency_percentage"),
                score=score.get("sleep_performance_percentage"),
                heart_rate_avg=score.get("respiratory_rate"),
                respiratory_rate_avg=score.get("respiratory_rate"),
            ))
        return records

    def get_recovery(self, start: Optional[date] = None, end: Optional[date] = None) -> List[RecoveryRecord]:
        start = start or date.today() - timedelta(days=7)
        end = end or date.today()
        data = self._request("GET", "/v1/recovery", params={
            "start": start.isoformat(),
            "end": end.isoformat(),
        })
        records = []
        for item in data.get("records", []):
            score = item.get("score", {})
            records.append(RecoveryRecord(
                source=PROVIDER,
                date=item.get("created_at", "")[:10],
                score=int(score.get("recovery_score", 0)),
                hrv_ms=score.get("hrv_rmssd_milli"),
                resting_hr=score.get("resting_heart_rate"),
                spo2=score.get("spo2_percentage"),
                skin_temp_celsius=score.get("skin_temp_celsius"),
            ))
        return records

    def get_workouts(self, start: Optional[date] = None, end: Optional[date] = None) -> List[ActivityRecord]:
        start = start or date.today() - timedelta(days=7)
        end = end or date.today()
        data = self._request("GET", "/v1/activity/workout", params={
            "start": start.isoformat(),
            "end": end.isoformat(),
        })
        records = []
        for item in data.get("records", []):
            score = item.get("score", {})
            records.append(ActivityRecord(
                source=PROVIDER,
                date=item.get("during", {}).get("lower", "")[:10],
                activity_type=item.get("sport_id", {}).get("name"),
                duration_seconds=score.get("end", 0) - score.get("start", 0) if score.get("end") else None,
                calories=score.get("kilojoule", 0) * 0.239006 if score.get("kilojoule") else None,
                avg_hr=score.get("average_heart_rate"),
                max_hr=score.get("max_heart_rate"),
                strain=score.get("strain"),
            ))
        return records

    def close(self):
        if self._client:
            self._client.close()
            self._client = None
