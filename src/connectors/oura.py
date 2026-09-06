"""Oura Ring API client — https://cloud.ouraring.com/v2/docs"""

from datetime import date, timedelta
from typing import List, Optional

import httpx

from ..auth import get_tokens, refresh_token, save_provider_tokens
from ..config import Settings
from ..models.activity import ActivityRecord
from ..models.recovery import RecoveryRecord
from ..models.sleep import SleepRecord

PROVIDER = "oura"


class OuraClient:
    def __init__(self, settings: Optional[Settings] = None):
        self.settings = settings or Settings()
        self.base = self.settings.oura.api_base
        self._client: Optional[httpx.Client] = None

    def _get_client(self) -> httpx.Client:
        if self._client:
            return self._client

        tokens = get_tokens(PROVIDER)
        if not tokens:
            raise RuntimeError("Oura not authorized. Run: python -m src.auth")

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

    def _collect(self, path: str, start: Optional[date], end: Optional[date]) -> List[dict]:
        """Fetch every page of a usercollection endpoint.

        Oura returns a next_token whenever the range exceeds one page; without
        following it we would silently drop the older days of the range.
        """
        start = start or date.today() - timedelta(days=7)
        end = end or date.today()
        params = {"start_date": start.isoformat(), "end_date": end.isoformat()}

        rows: List[dict] = []
        while True:
            page = self._request("GET", path, params=params)
            rows.extend(page.get("data", []))
            next_token = page.get("next_token")
            if not next_token:
                return rows
            params["next_token"] = next_token

    def get_sleep(self, start: Optional[date] = None, end: Optional[date] = None) -> List[SleepRecord]:
        daily = self._collect("/usercollection/daily_sleep", start, end)
        details_by_day = {
            s["day"]: s for s in self._collect("/usercollection/sleep", start, end)
        }

        records = []
        for item in daily:
            day = item.get("day", "")
            detail = details_by_day.get(day, {})
            records.append(SleepRecord(
                source=PROVIDER,
                date=day,
                total_sleep_seconds=detail.get("total_sleep_duration") or item.get("contributors", {}).get("total_sleep", 0),
                rem_seconds=detail.get("rem_sleep_duration"),
                deep_seconds=detail.get("deep_sleep_duration"),
                light_seconds=detail.get("light_sleep_duration"),
                awake_seconds=detail.get("awake_time"),
                efficiency=detail.get("efficiency"),
                score=item.get("score"),
                heart_rate_avg=detail.get("average_heart_rate"),
                hrv_avg=detail.get("average_hrv"),
                respiratory_rate_avg=detail.get("average_breath"),
                start_time=detail.get("bedtime_start"),
                end_time=detail.get("bedtime_end"),
            ))
        return records

    def get_readiness(self, start: Optional[date] = None, end: Optional[date] = None) -> List[RecoveryRecord]:
        records = []
        for item in self._collect("/usercollection/daily_readiness", start, end):
            contributors = item.get("contributors", {})
            records.append(RecoveryRecord(
                source=PROVIDER,
                date=item.get("day", ""),
                score=item.get("score"),
                hrv_ms=contributors.get("hrv_balance"),
                resting_hr=contributors.get("resting_heart_rate"),
                skin_temp_celsius=contributors.get("body_temperature"),
            ))
        return records

    def get_activity(self, start: Optional[date] = None, end: Optional[date] = None) -> List[ActivityRecord]:
        records = []
        for item in self._collect("/usercollection/daily_activity", start, end):
            records.append(ActivityRecord(
                source=PROVIDER,
                date=item.get("day", ""),
                activity_type="daily",
                calories=item.get("total_calories"),
                steps=item.get("steps"),
                distance_meters=item.get("equivalent_walking_distance"),
            ))
        return records

    def get_spo2(self, start: Optional[date] = None, end: Optional[date] = None) -> dict:
        start = start or date.today() - timedelta(days=7)
        end = end or date.today()
        return self._request("GET", "/usercollection/daily_spo2", params={
            "start_date": start.isoformat(),
            "end_date": end.isoformat(),
        })

    def close(self):
        if self._client:
            self._client.close()
            self._client = None
