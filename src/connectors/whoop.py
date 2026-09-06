"""Whoop API v2 client — https://developer.whoop.com/api

v1 was sunset; all collection endpoints live under /v2 and page via next_token.
"""

from datetime import date, datetime, timedelta, timezone
from typing import List, Optional

import httpx

from ..auth import get_tokens, refresh_token, save_provider_tokens
from ..config import Settings
from ..models.activity import ActivityRecord
from ..models.recovery import RecoveryRecord
from ..models.sleep import SleepRecord

PROVIDER = "whoop"


def _parse_ts(value: Optional[str]) -> Optional[datetime]:
    """Parse an ISO-8601 timestamp, tolerating the trailing 'Z'.

    datetime.fromisoformat only learned to accept 'Z' in 3.11, and this runs
    on 3.9 too.
    """
    if not value:
        return None
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None


def _offset(value: Optional[str]) -> Optional[timezone]:
    """Turn Whoop's '+02:00' / '-05:00' timezone_offset into a tzinfo."""
    if not value or len(value) < 6 or value[0] not in "+-":
        return None
    try:
        delta = timedelta(hours=int(value[1:3]), minutes=int(value[4:6]))
    except ValueError:
        return None
    return timezone(-delta if value[0] == "-" else delta)


def _local(ts: Optional[str], tz_offset: Optional[str]) -> Optional[datetime]:
    """Parse a UTC timestamp and shift it into the member's local zone.

    Whoop reports instants in UTC with the local offset alongside. Bedtime is
    only meaningful locally — reported in UTC, a 00:35 bedtime in Madrid reads
    as 22:35 the previous day.
    """
    moment = _parse_ts(ts)
    tz = _offset(tz_offset)
    return moment.astimezone(tz) if moment and tz else moment


def _day(value: Optional[str]) -> str:
    return value[:10] if value else ""


def _seconds(millis: Optional[int]) -> Optional[int]:
    return millis // 1000 if millis is not None else None


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

    def _collect(self, path: str, start: Optional[date], end: Optional[date]) -> List[dict]:
        """Fetch every page of a collection endpoint.

        Whoop caps each response at 25 records, so a week of workouts can span
        several pages; without following next_token we would silently truncate.
        """
        start = start or date.today() - timedelta(days=7)
        end = end or date.today()
        params = {
            "start": _iso_utc(start),
            "end": _iso_utc(end, end_of_day=True),
            "limit": 25,
        }

        records: List[dict] = []
        while True:
            page = self._request("GET", path, params=params)
            records.extend(page.get("records", []))
            next_token = page.get("next_token")
            if not next_token:
                return records
            params["nextToken"] = next_token

    def get_sleep(self, start: Optional[date] = None, end: Optional[date] = None) -> List[SleepRecord]:
        records = []
        for item in self._collect("/v2/activity/sleep", start, end):
            score = item.get("score") or {}
            stages = score.get("stage_summary") or {}

            in_bed = stages.get("total_in_bed_time_milli")
            awake = stages.get("total_awake_time_milli") or 0
            no_data = stages.get("total_no_data_time_milli") or 0
            # in_bed includes time awake; actual sleep is what's left over.
            asleep = (in_bed - awake - no_data) if in_bed is not None else None

            tz_offset = item.get("timezone_offset")
            began = _local(item.get("start"), tz_offset)
            ended = _local(item.get("end"), tz_offset)

            records.append(SleepRecord(
                source=PROVIDER,
                # Keyed on the local day you woke up, so a night lines up with
                # the recovery Whoop scores that same morning.
                date=(ended or began).date().isoformat() if (ended or began) else "",
                total_sleep_seconds=_seconds(asleep) or 0,
                rem_seconds=_seconds(stages.get("total_rem_sleep_time_milli")),
                deep_seconds=_seconds(stages.get("total_slow_wave_sleep_time_milli")),
                light_seconds=_seconds(stages.get("total_light_sleep_time_milli")),
                awake_seconds=_seconds(stages.get("total_awake_time_milli")),
                efficiency=score.get("sleep_efficiency_percentage"),
                score=score.get("sleep_performance_percentage"),
                respiratory_rate_avg=score.get("respiratory_rate"),
                start_time=began,
                end_time=ended,
                is_nap=bool(item.get("nap")),
            ))
        return records

    def get_recovery(self, start: Optional[date] = None, end: Optional[date] = None) -> List[RecoveryRecord]:
        records = []
        for item in self._collect("/v2/recovery", start, end):
            score = item.get("score") or {}
            records.append(RecoveryRecord(
                source=PROVIDER,
                date=_day(item.get("created_at")),
                score=score.get("recovery_score"),
                hrv_ms=score.get("hrv_rmssd_milli"),
                resting_hr=score.get("resting_heart_rate"),
                spo2=score.get("spo2_percentage"),
                skin_temp_celsius=score.get("skin_temp_celsius"),
            ))
        return records

    def get_workouts(self, start: Optional[date] = None, end: Optional[date] = None) -> List[ActivityRecord]:
        records = []
        for item in self._collect("/v2/activity/workout", start, end):
            score = item.get("score") or {}
            began, ended = _parse_ts(item.get("start")), _parse_ts(item.get("end"))
            kilojoule = score.get("kilojoule")

            records.append(ActivityRecord(
                source=PROVIDER,
                date=_day(item.get("start")),
                # v2 renamed sport_id to sport_name; accept either.
                activity_type=item.get("sport_name") or item.get("sport_id"),
                start_time=began,
                end_time=ended,
                duration_seconds=int((ended - began).total_seconds()) if began and ended else None,
                calories=kilojoule * 0.239006 if kilojoule is not None else None,
                avg_hr=score.get("average_heart_rate"),
                max_hr=score.get("max_heart_rate"),
                strain=score.get("strain"),
                distance_meters=score.get("distance_meter"),
            ))
        return records

    def close(self):
        if self._client:
            self._client.close()
            self._client = None


def _iso_utc(day: date, end_of_day: bool = False) -> str:
    """Render a date as the UTC instant Whoop's start/end params expect."""
    moment = datetime.combine(
        day,
        datetime.max.time() if end_of_day else datetime.min.time(),
        tzinfo=timezone.utc,
    )
    return moment.isoformat().replace("+00:00", "Z")
