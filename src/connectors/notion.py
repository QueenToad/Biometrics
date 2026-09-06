"""Notion API client — writes one row per day into the biometrics database.

Upserts on the "День" date property so re-running a sync corrects a day in
place instead of piling up duplicate rows.
"""

from typing import List, Optional

import httpx

from ..config import Settings
from ..models.daily import DailyRecord

API = "https://api.notion.com/v1"
NOTION_VERSION = "2022-06-28"


class NotionClient:
    def __init__(self, settings: Optional[Settings] = None):
        self.settings = settings or Settings()
        cfg = self.settings.notion
        if not cfg.token or not cfg.database_id:
            raise RuntimeError(
                "Notion is not configured. Set NOTION_TOKEN and NOTION_DATABASE_ID in .env"
            )
        self.database_id = cfg.database_id
        self._client = httpx.Client(
            base_url=API,
            headers={
                "Authorization": f"Bearer {cfg.token}",
                "Notion-Version": NOTION_VERSION,
                "Content-Type": "application/json",
            },
            timeout=30,
        )

    def _request(self, method: str, path: str, **kwargs) -> dict:
        resp = self._client.request(method, path, **kwargs)
        if resp.status_code >= 400:
            # Notion puts the useful part in the body; the status alone is not
            # enough to tell a bad token from an unshared database.
            raise RuntimeError(f"Notion {resp.status_code}: {resp.text}")
        return resp.json()

    def _find_page(self, day: str) -> Optional[str]:
        """Return the page id already holding this day, if any."""
        result = self._request(
            "POST",
            f"/databases/{self.database_id}/query",
            json={
                "filter": {"property": "День", "date": {"equals": day}},
                "page_size": 1,
            },
        )
        results = result.get("results", [])
        return results[0]["id"] if results else None

    @staticmethod
    def _properties(rec: DailyRecord) -> dict:
        def num(v):
            return {"number": v}

        def text(v):
            return {"rich_text": [{"text": {"content": v}}] if v else []}

        props = {
            "Дата": {"title": [{"text": {"content": rec.day}}]},
            "День": {"date": {"start": rec.day}},
            "Отбой": text(rec.bedtime),
            "Подъём": text(rec.wake_time),
            "Сон, ч": num(rec.sleep_hours),
            "Sleep score": num(rec.sleep_score),
            "Recovery": num(rec.recovery_score),
            "HRV": num(rec.hrv_ms),
            "RHR": num(rec.resting_hr),
            "REM, ч": num(rec.rem_hours),
            "Глубокий, ч": num(rec.deep_hours),
            "Дневной сон": {"checkbox": rec.had_nap},
            "Активность, ккал": num(rec.activity_calories),
            "Тренировки": text(rec.workouts),
        }
        if rec.sources:
            props["Источник"] = {"select": {"name": rec.sources}}
        return props

    def upsert(self, rec: DailyRecord) -> str:
        """Create or update the row for one day. Returns 'created' or 'updated'."""
        props = self._properties(rec)
        page_id = self._find_page(rec.day)
        if page_id:
            self._request("PATCH", f"/pages/{page_id}", json={"properties": props})
            return "updated"
        self._request(
            "POST",
            "/pages",
            json={"parent": {"database_id": self.database_id}, "properties": props},
        )
        return "created"

    def upsert_all(self, records: List[DailyRecord]) -> dict:
        counts = {"created": 0, "updated": 0}
        for rec in sorted(records, key=lambda r: r.day):
            counts[self.upsert(rec)] += 1
        return counts

    def close(self):
        self._client.close()
