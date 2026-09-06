"""Notion API client — one child page per day, under a parent page.

Each day's page carries a section per device rather than one merged set of
numbers: Whoop and Oura measure differently, and the gap between them is
itself worth seeing.
"""

from typing import Dict, List, Optional

import httpx

from ..config import Settings
from ..models.daily import DailyRecord

API = "https://api.notion.com/v1"
NOTION_VERSION = "2022-06-28"

DEVICE_LABEL = {"whoop": "Whoop", "oura": "Oura"}


class NotionClient:
    def __init__(self, settings: Optional[Settings] = None):
        self.settings = settings or Settings()
        cfg = self.settings.notion
        if not cfg.token or not cfg.parent_page_id:
            raise RuntimeError(
                "Notion is not configured. Set NOTION_TOKEN and NOTION_PARENT_PAGE_ID in .env"
            )
        self.parent_page_id = cfg.parent_page_id
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
            # The body distinguishes a bad token from a page that was never
            # shared with the integration; the status alone does not.
            raise RuntimeError(f"Notion {resp.status_code}: {resp.text}")
        return resp.json()

    # --- reading what's already there -------------------------------------

    def _existing_pages(self) -> Dict[str, str]:
        """Map day -> page id for the child pages already under the parent."""
        found: Dict[str, str] = {}
        cursor = None
        while True:
            params = {"page_size": 100}
            if cursor:
                params["start_cursor"] = cursor
            page = self._request(
                "GET", f"/blocks/{self.parent_page_id}/children", params=params
            )
            for block in page.get("results", []):
                if block.get("type") == "child_page":
                    title = block["child_page"].get("title", "")
                    if title:
                        found[title] = block["id"]
            if not page.get("has_more"):
                return found
            cursor = page.get("next_cursor")

    def _clear_page(self, page_id: str) -> None:
        """Delete a page's blocks so it can be rewritten from scratch.

        Notion has no replace-content call, and appending to yesterday's blocks
        would leave both versions on the page.
        """
        cursor = None
        block_ids = []
        while True:
            params = {"page_size": 100}
            if cursor:
                params["start_cursor"] = cursor
            page = self._request("GET", f"/blocks/{page_id}/children", params=params)
            block_ids += [b["id"] for b in page.get("results", [])]
            if not page.get("has_more"):
                break
            cursor = page.get("next_cursor")

        for block_id in block_ids:
            self._request("DELETE", f"/blocks/{block_id}")

    # --- rendering --------------------------------------------------------

    @staticmethod
    def _text(content: str, bold: bool = False) -> dict:
        return {
            "type": "text",
            "text": {"content": content},
            "annotations": {"bold": bold},
        }

    @classmethod
    def _line(cls, label: str, value: str) -> dict:
        return {
            "object": "block",
            "type": "bulleted_list_item",
            "bulleted_list_item": {
                "rich_text": [cls._text(f"{label}: ", bold=True), cls._text(value)]
            },
        }

    @classmethod
    def _heading(cls, text: str) -> dict:
        return {
            "object": "block",
            "type": "heading_2",
            "heading_2": {"rich_text": [cls._text(text)]},
        }

    @classmethod
    def _paragraph(cls, text: str) -> dict:
        return {
            "object": "block",
            "type": "paragraph",
            "paragraph": {"rich_text": [cls._text(text)] if text else []},
        }

    @classmethod
    def _device_blocks(cls, rec: DailyRecord) -> List[dict]:
        blocks = [cls._heading(DEVICE_LABEL.get(rec.source, rec.source))]

        def fmt(value, suffix: str = "") -> Optional[str]:
            return None if value is None else f"{value}{suffix}"

        rows = [
            ("Отбой", rec.bedtime),
            ("Подъём", rec.wake_time),
            ("Сон", fmt(rec.sleep_hours, " ч")),
            ("Sleep score", fmt(rec.sleep_score)),
            ("Recovery", fmt(rec.recovery_score)),
            ("HRV", fmt(rec.hrv_ms, " мс")),
            ("Пульс покоя", fmt(int(rec.resting_hr) if rec.resting_hr else None, " уд/мин")),
            ("REM", fmt(rec.rem_hours, " ч")),
            ("Глубокий сон", fmt(rec.deep_hours, " ч")),
            ("Активность", fmt(rec.activity_calories, " ккал")),
            ("Тренировки", rec.workouts),
        ]
        blocks += [cls._line(label, value) for label, value in rows if value]

        if rec.had_nap:
            blocks.append(cls._line("Дневной сон", "был"))
        if len(blocks) == 1:
            blocks.append(cls._paragraph("Данных за этот день нет."))
        return blocks

    @classmethod
    def _page_blocks(cls, records: List[DailyRecord]) -> List[dict]:
        blocks: List[dict] = []
        for source in ("whoop", "oura"):
            for rec in records:
                if rec.source == source:
                    blocks += cls._device_blocks(rec)
        return blocks or [cls._paragraph("Данных за этот день нет.")]

    # --- writing ----------------------------------------------------------

    def upsert_day(self, day: str, records: List[DailyRecord],
                   existing: Optional[Dict[str, str]] = None) -> str:
        """Create or rewrite the page for one day. Returns 'created'/'updated'."""
        blocks = self._page_blocks(records)
        pages = self._existing_pages() if existing is None else existing
        page_id = pages.get(day)

        if page_id:
            self._clear_page(page_id)
            self._request("PATCH", f"/blocks/{page_id}/children", json={"children": blocks})
            return "updated"

        self._request("POST", "/pages", json={
            "parent": {"page_id": self.parent_page_id},
            "properties": {"title": {"title": [{"text": {"content": day}}]}},
            "children": blocks,
        })
        return "created"

    def upsert_all(self, records: List[DailyRecord]) -> dict:
        by_day: Dict[str, List[DailyRecord]] = {}
        for rec in records:
            by_day.setdefault(rec.day, []).append(rec)

        # Listing the parent's children once keeps this to one request per day.
        existing = self._existing_pages()
        counts = {"created": 0, "updated": 0}
        for day in sorted(by_day):
            counts[self.upsert_day(day, by_day[day], existing)] += 1
        return counts

    def close(self):
        self._client.close()
