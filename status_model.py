#!/usr/bin/env python3
"""
Pure status-model helpers for InkDash.

This module intentionally contains no file I/O and no HTTP code, so app.py can
keep route handling while tests can exercise status normalization directly.
"""

from datetime import datetime
from typing import Any, Dict, Optional


MAX_EVENT_ITEMS = 8


def now_display() -> str:
    """Return a local timestamp for e-ink display and API payloads."""
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")


def parse_display_time(value: Any) -> Optional[datetime]:
    """Parse the local display timestamp used by status records."""
    try:
        return datetime.strptime(str(value), "%Y-%m-%d %H:%M:%S")
    except (TypeError, ValueError):
        return None


def is_status_stale(
    status: Dict[str, Any],
    stale_after_seconds: int,
    now: Optional[datetime] = None,
) -> bool:
    """Return true when a status record has not been updated recently."""
    updated_at = parse_display_time(status.get("updated_at"))
    if not updated_at:
        return False

    current_time = now or datetime.now()
    age_seconds = (current_time - updated_at).total_seconds()
    return age_seconds > stale_after_seconds


def default_status() -> Dict[str, Any]:
    """Build the default status shown before an agent/script writes updates."""
    timestamp = now_display()
    return {
        "title": "状态看板",
        "state": "待更新",
        "project": "未指定项目",
        "branch": "未指定分支",
        "objective": "等待 agent 或脚本写入当前目标。",
        "current_task": "暂无正在展示的任务。",
        "next_action": "通过 POST /api/status 写入最新状态；旧脚本仍可使用 /api/vibe。",
        "blockers": [],
        "participants": [],
        "updated_at": timestamp,
        "events": [
            {
                "time": timestamp,
                "text": "InkDash 已启动，等待状态更新。"
            }
        ]
    }


def clean_text(value: Any, fallback: str = "") -> str:
    """Normalize a scalar value into display-safe text."""
    text = str(value).strip() if value is not None else ""
    return text if text else fallback


def text_list(value: Any) -> list:
    """Normalize a value into a list of non-empty text items."""
    if value is None:
        return []
    if isinstance(value, list):
        return [clean_text(item) for item in value if clean_text(item)]
    text = clean_text(value)
    return [text] if text else []


def event_list(value: Any) -> list:
    """Normalize a value into bounded event records."""
    if not isinstance(value, list):
        return []

    events = []
    for item in value:
        if isinstance(item, dict):
            text = clean_text(item.get("text"))
            if not text:
                continue
            events.append({
                "time": clean_text(item.get("time"), now_display()),
                "text": text
            })
        else:
            text = clean_text(item)
            if text:
                events.append({"time": now_display(), "text": text})

    return events[-MAX_EVENT_ITEMS:]


def normalize_status(raw: Any) -> Dict[str, Any]:
    """Normalize status data so rendering and API output stay predictable."""
    status = default_status()
    if not isinstance(raw, dict):
        return status

    text_fields = [
        "title",
        "state",
        "project",
        "branch",
        "objective",
        "current_task",
        "next_action",
        "updated_at",
    ]
    for field in text_fields:
        if field in raw:
            status[field] = clean_text(raw.get(field), status[field])

    for field in ("blockers", "participants"):
        if field in raw:
            status[field] = text_list(raw.get(field))

    if "events" in raw:
        status["events"] = event_list(raw.get("events"))

    return status


def merge_status_patch(status: Dict[str, Any], patch: Dict[str, Any]) -> Dict[str, Any]:
    """Merge an API patch into a normalized status object."""
    if not isinstance(patch, dict):
        raise ValueError("JSON body must be an object")

    merged = normalize_status(status)
    text_fields = [
        "title",
        "state",
        "project",
        "branch",
        "objective",
        "current_task",
        "next_action",
    ]
    for field in text_fields:
        if field in patch:
            merged[field] = clean_text(patch.get(field), merged[field])

    for field in ("blockers", "participants"):
        if field in patch:
            merged[field] = text_list(patch.get(field))

    if "events" in patch:
        merged["events"] = event_list(patch.get("events"))

    event_text = clean_text(patch.get("event"))
    if event_text:
        merged.setdefault("events", [])
        merged["events"].append({"time": now_display(), "text": event_text})
        merged["events"] = merged["events"][-MAX_EVENT_ITEMS:]

    merged["updated_at"] = now_display()
    return merged
