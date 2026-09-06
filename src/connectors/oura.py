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
            tokens = get_tokens(PROVIDER) or {}
            if not tokens.get("refresh_token"):
                raise RuntimeError(
                    "Oura access token expired and there is no refresh token to renew it.\n"
                    "Re-authorize once: python -m src.auth oura"
                )
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

    # Oura labels each sleep period. Only long_sleep is the main night; the
    # rest are naps and must not stand in for it.
    NIGHT_TYPES = ("long_sleep",)
    NAP_TYPES = ("late_nap", "rest")

    def _sleep_periods(self, start: Optional[date], end: Optional[date]) -> List[dict]:
        return [p for p in self._collect("/usercollection/sleep", start, end)
                if p.get("type") != "deleted"]

    @classmethod
    def _is_nap(cls, period: dict) -> bool:
        kind = period.get("type")
        if kind in cls.NIGHT_TYPES:
            return False
        if kind in cls.NAP_TYPES:
            return True
        # An unlabelled short period is a nap, not a night.
        return (period.get("total_sleep_duration") or 0) < 3 * 3600

    def get_sleep(self, start: Optional[date] = None, end: Optional[date] = None) -> List[SleepRecord]:
        scores = {d["day"]: d.get("score")
                  for d in self._collect("/usercollection/daily_sleep", start, end)}

        records = []
        for period in self._sleep_periods(start, end):
            day = period.get("day", "")
            is_nap = self._is_nap(period)
            records.append(SleepRecord(
                source=PROVIDER,
                date=day,
                total_sleep_seconds=period.get("total_sleep_duration") or 0,
                rem_seconds=period.get("rem_sleep_duration"),
                deep_seconds=period.get("deep_sleep_duration"),
                light_seconds=period.get("light_sleep_duration"),
                awake_seconds=period.get("awake_time"),
                efficiency=period.get("efficiency"),
                # The daily score grades the night, so it doesn't apply to a nap.
                score=None if is_nap else scores.get(day),
                heart_rate_avg=period.get("average_heart_rate"),
                hrv_avg=period.get("average_hrv"),
                respiratory_rate_avg=period.get("average_breath"),
                start_time=period.get("bedtime_start"),
                end_time=period.get("bedtime_end"),
                is_nap=is_nap,
            ))
        return records

    def get_readiness(self, start: Optional[date] = None, end: Optional[date] = None) -> List[RecoveryRecord]:
        """Readiness score, with HRV and resting heart rate from that night.

        daily_readiness.contributors holds each factor's contribution to the
        score on a 0-100 scale, not the measurement itself — reading
        contributors.resting_heart_rate as a pulse gives values like 9 bpm.
        The physiological numbers live on the sleep period.
        """
        nights = {}
        for period in self._sleep_periods(start, end):
            if not self._is_nap(period):
                nights[period.get("day", "")] = period

        records = []
        for item in self._collect("/usercollection/daily_readiness", start, end):
            day = item.get("day", "")
            night = nights.get(day, {})
            records.append(RecoveryRecord(
                source=PROVIDER,
                date=day,
                score=item.get("score"),
                hrv_ms=night.get("average_hrv"),
                resting_hr=night.get("lowest_heart_rate"),
                skin_temp_celsius=item.get("temperature_deviation"),
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
