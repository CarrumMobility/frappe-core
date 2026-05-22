"""Agent Performance analytics dashboard (pivot data for CRM UI)."""

from __future__ import annotations

import hashlib
import json
import random
from calendar import month_name
from datetime import date, datetime, timedelta

import frappe
from frappe.utils import flt, getdate

from core.constants.enums import EnumValues

MOCK_AGENTS = [
    {"id": "rahul@carrum.co.in", "name": "Rahul Sharma", "city": "Delhi"},
    {"id": "priya@carrum.co.in", "name": "Priya Singh", "city": "Mumbai"},
    {"id": "amit@carrum.co.in", "name": "Amit Kumar", "city": "Delhi"},
]

AGENT_PERFORMANCE_DOCTYPE = "Agent Performance"
CALL_SESSION_DOCTYPE = "Call Session"
EVENT_DOCTYPE = "Event"

_PERFORMANCE_FETCH_FIELDS = [
    "name",
    "date",
    "agent_id",
    "agent_name",
    "hubId",
    "hubName",
    "login_duration",
    "dialer_session_duration",
    "dialer_talktime_duration",
    "click2call_talktime_duration",
    "break_duration",
    "break_count",
    "dispose_duration",
    "click2call_ring_time",
    "click2call_ring_duration",
    "total_dialer_connects",
    "total_click2call_attempts",
    "total_click2call_connects",
    "total_unique_attempts",
    "total_unique_connects",
    "total_unique_interests",
    "unique_schedules_walkin",
    "total_manual_attempts",
    "total_manual_connects",
    "total_mannual_attempts",
    "total_mannual_connects",
    "dialer_session_count",
    "schedules_followup",
    "scheduled_followup",
    "completed_scheduled_followup",
    "new_walkin_schedules",
    "scheduled_walkin",
    "completed_scheduled_walkin",
    "psd_count",
    "fsd_count",
    "walkin_count",
]

# Metrics that open the breakup drawer when a value cell is clicked
CLICKABLE_METRICS = frozenset(
    {
        "dialer_session_duration",
        "break_duration",
        "total_attempts",
        "total_connects",
        "schedules_followup",
        "followup_done",
        "new_walkin_schedules",
        "walkin_done",
    }
)

_PLACEHOLDER_PCT_69 = 69.0


def _agent_performance_table_ready() -> bool:
    return bool(frappe.db.exists("DocType", AGENT_PERFORMANCE_DOCTYPE))


def _agent_performance_table_columns() -> set[str]:
    if not _agent_performance_table_ready():
        return set()
    return set(frappe.db.get_table_columns(AGENT_PERFORMANCE_DOCTYPE) or [])


def _performance_fetch_fields() -> list[str]:
    """Only columns that exist in MariaDB (DocType meta can be ahead of DB)."""
    cols = _agent_performance_table_columns()
    if not cols:
        return ["name"]

    out: list[str] = []
    for fieldname in _PERFORMANCE_FETCH_FIELDS:
        if fieldname in cols and fieldname not in out:
            out.append(fieldname)

    if (
        "unique_schedules_walkin" not in out
        and "unique_date_confirmed" in cols
        and "unique_date_confirmed" not in out
    ):
        out.append("unique_date_confirmed")

    return out or ["name"]


def _duration_to_seconds(value) -> int:
    if value is None:
        return 0
    if isinstance(value, int):
        return max(0, value)
    if isinstance(value, float):
        return max(0, int(value))
    return max(0, int(flt(value) or 0))


def _int_field(row: dict, key: str, *fallback_keys: str) -> int:
    for k in (key,) + fallback_keys:
        if k and row.get(k) is not None:
            return max(0, int(flt(row.get(k)) or 0))
    return 0


def _format_doc_date(value) -> str:
    if value is None:
        return ""
    if isinstance(value, datetime):
        return value.date().strftime("%Y-%m-%d")
    if isinstance(value, date):
        return value.strftime("%Y-%m-%d")
    s = str(value).strip()
    return s[:10] if s else ""


def _normalize_db_row(row: dict) -> dict:
    """Map Agent Performance doc row to internal analytics doc (field names used by metrics)."""
    ring_raw = row.get("click2call_ring_time")
    if ring_raw is None:
        ring_raw = row.get("click2call_ring_duration")
    c2c_attempts = _int_field(row, "total_click2call_attempts")
    c2c_connects = _int_field(row, "total_click2call_connects")
    return {
        "date": _format_doc_date(row.get("date")),
        "agent_id": (row.get("agent_id") or "").strip(),
        "agent_name": (row.get("agent_name") or "").strip(),
        "hub_id": (row.get("hubId") or "").strip(),
        "hub_name": (row.get("hubName") or "").strip(),
        "city": (row.get("hubName") or "").strip(),
        "login_duration": _duration_to_seconds(row.get("login_duration")),
        "dialer_session_duration": _duration_to_seconds(row.get("dialer_session_duration")),
        "dialer_talktime_duration": _duration_to_seconds(row.get("dialer_talktime_duration")),
        "click2call_talktime_duration": _duration_to_seconds(row.get("click2call_talktime_duration")),
        "break_duration": _duration_to_seconds(row.get("break_duration")),
        "break_count": _int_field(row, "break_count"),
        "dispose_duration": _duration_to_seconds(row.get("dispose_duration")),
        "click2call_ring_time": _duration_to_seconds(ring_raw),
        "dialer_session_count": _int_field(row, "dialer_session_count"),
        "total_dialer_connects": _int_field(row, "total_dialer_connects"),
        "total_click2call_attempts": c2c_attempts,
        "total_click2call_connects": c2c_connects,
        "total_unique_attempts": _int_field(row, "total_unique_attempts"),
        "total_unique_connects": _int_field(row, "total_unique_connects"),
        "total_unique_interests": _int_field(row, "total_unique_interests"),
        "unique_schedules_walkin": _int_field(row, "unique_schedules_walkin"),
        "schedules_followup": _int_field(row, "schedules_followup"),
        "scheduled_followup": _int_field(row, "scheduled_followup"),
        "completed_scheduled_followup": _int_field(row, "completed_scheduled_followup"),
        "new_walkin_schedules": _int_field(row, "new_walkin_schedules"),
        "scheduled_walkin": _int_field(row, "scheduled_walkin"),
        "completed_scheduled_walkin": _int_field(row, "completed_scheduled_walkin"),
        "psd_count": _int_field(row, "psd_count"),
        "fsd_count": _int_field(row, "fsd_count"),
        "walkin_count": _int_field(row, "walkin_count"),
    }


def _fetch_date_bounds_from_db() -> list[str]:
    if not _agent_performance_table_ready():
        return []
    min_d, max_d = frappe.db.sql(
        "select min(`date`), max(`date`) from `tabAgent Performance`"
    )[0]
    if not min_d or not max_d:
        return []
    return [_format_doc_date(min_d), _format_doc_date(max_d)]


def _fetch_distinct_hubs_from_db() -> list[dict]:
    """Unique hubs from Agent Performance (UI shows hubName; filter value is hubId)."""
    if not _agent_performance_table_ready():
        return []
    rows = frappe.get_all(
        AGENT_PERFORMANCE_DOCTYPE,
        fields=["hubId", "hubName"],
        limit_page_length=0,
    )
    by_hub: dict[str, str] = {}
    for r in rows or []:
        hid = (r.get("hubId") or "").strip()
        if not hid:
            continue
        hname = (r.get("hubName") or "").strip() or hid
        if hid not in by_hub:
            by_hub[hid] = hname
    return [{"id": k, "name": v} for k, v in sorted(by_hub.items(), key=lambda kv: (kv[1].lower(), kv[0]))]


def _fetch_agents_meta_from_db() -> list[dict]:
    """Distinct agents with hub_ids for city filter (hubId = city filter value)."""
    if not _agent_performance_table_ready():
        return []
    rows = frappe.get_all(
        AGENT_PERFORMANCE_DOCTYPE,
        fields=["agent_id", "agent_name", "hubId", "hubName"],
        limit_page_length=0,
    )
    by_id: dict[str, dict] = {}
    for r in rows or []:
        aid = (r.get("agent_id") or "").strip()
        if not aid:
            continue
        hub = (r.get("hubId") or "").strip()
        if aid not in by_id:
            by_id[aid] = {
                "id": aid,
                "name": (r.get("agent_name") or aid).strip(),
                "hub_ids": set(),
                "_any_hub_name": "",
            }
        if hub:
            by_id[aid]["hub_ids"].add(hub)
            if not by_id[aid]["_any_hub_name"] and (r.get("hubName") or "").strip():
                by_id[aid]["_any_hub_name"] = (r.get("hubName") or "").strip()

    out = []
    for a in by_id.values():
        hub_ids = sorted(a["hub_ids"])
        hub_name = a.pop("_any_hub_name", "") or ""
        a["hub_ids"] = hub_ids
        # Legacy UI field used for labels; primary label from first known hub name
        a["city"] = hub_name
        out.append(a)
    out.sort(key=lambda x: (x["name"] or "").lower())
    return out


def _fetch_performance_docs_from_db(
    *,
    from_date: str | None,
    to_date: str | None,
    agent_ids: list[str] | None,
    hub_id: str,
) -> list[dict]:
    if not _agent_performance_table_ready():
        return []

    filters: dict = {}
    if from_date and to_date:
        filters["date"] = ["between", [from_date, to_date]]
    elif from_date:
        filters["date"] = [">=", from_date]
    elif to_date:
        filters["date"] = ["<=", to_date]

    if agent_ids:
        filters["agent_id"] = ("in", agent_ids)

    if hub_id:
        filters["hubId"] = hub_id

    rows = frappe.get_all(
        AGENT_PERFORMANCE_DOCTYPE,
        filters=filters or None,
        fields=_performance_fetch_fields(),
        limit_page_length=0,
        order_by="date asc, agent_id asc",
    )

    return [_normalize_db_row(r) for r in (rows or []) if _normalize_db_row(r).get("date")]


def _agents_for_pivot(
    docs: list[dict],
    restricted_ids: list[str] | None,
    meta_by_id: dict[str, dict],
) -> list[dict]:
    """Distinct agents appearing in docs, enriched with hub_ids for UI."""
    allowed = set(restricted_ids) if restricted_ids else None
    seen: set[str] = set()
    order: list[str] = []
    for d in docs:
        aid = d.get("agent_id")
        if not aid:
            continue
        if allowed is not None and aid not in allowed:
            continue
        if aid not in seen:
            seen.add(aid)
            order.append(aid)
    agents = []
    for aid in order:
        name = next((d.get("agent_name") for d in docs if d.get("agent_id") == aid), aid)
        row = {"id": aid, "name": name or aid}
        m = meta_by_id.get(aid)
        if m:
            row["hub_ids"] = m.get("hub_ids", [])
            row["city"] = m.get("city", "")
        else:
            row["hub_ids"] = []
            row["city"] = ""
        agents.append(row)
    agents.sort(key=lambda x: (x.get("name") or "").lower())
    return agents


BASE_DOCS_BY_DATE = [
    {
        "date": "2026-05-14",
        "login_duration": 31680,
        "dialer_talktime_duration": 13158,
        "click2call_talktime_duration": 0,
        "break_duration": 760,
        "dispose_duration": 14942,
        "click2call_ring_duration": 0,
        "total_dialer_connects": 101,
        "total_manual_attempts": 18,
        "total_manual_connects": 12,
        "walkin_count": 0,
        "psd_count": 1,
        "fsd_count": 0,
    },
    {
        "date": "2026-05-13",
        "login_duration": 31487,
        "dialer_talktime_duration": 13158,
        "click2call_talktime_duration": 0,
        "break_duration": 760,
        "dispose_duration": 14942,
        "click2call_ring_duration": 14402,
        "total_dialer_connects": 127,
        "total_manual_attempts": 6,
        "total_manual_connects": 4,
        "walkin_count": 0,
        "psd_count": 1,
        "fsd_count": 0,
    },
    {
        "date": "2026-05-12",
        "login_duration": 33219,
        "dialer_talktime_duration": 15180,
        "click2call_talktime_duration": 0,
        "break_duration": 495,
        "dispose_duration": 819,
        "click2call_ring_duration": 815,
        "total_dialer_connects": 96,
        "total_manual_attempts": 3,
        "total_manual_connects": 2,
        "walkin_count": 2,
        "psd_count": 2,
        "fsd_count": 0,
    },
    {
        "date": "2026-05-11",
        "login_duration": 33168,
        "dialer_talktime_duration": 15123,
        "click2call_talktime_duration": 0,
        "break_duration": 622,
        "dispose_duration": 7976,
        "click2call_ring_duration": 4346,
        "total_dialer_connects": 99,
        "total_manual_attempts": 21,
        "total_manual_connects": 8,
        "walkin_count": 0,
        "psd_count": 1,
        "fsd_count": 1,
    },
    {
        "date": "2026-05-09",
        "login_duration": 32402,
        "dialer_talktime_duration": 14765,
        "click2call_talktime_duration": 0,
        "break_duration": 900,
        "dispose_duration": 414,
        "click2call_ring_duration": 374,
        "total_dialer_connects": 103,
        "total_manual_attempts": 8,
        "total_manual_connects": 5,
        "walkin_count": 0,
        "psd_count": 0,
        "fsd_count": 0,
    },
    {
        "date": "2026-05-08",
        "login_duration": 32374,
        "dialer_talktime_duration": 32383,
        "click2call_talktime_duration": 0,
        "break_duration": 585,
        "dispose_duration": 21572,
        "click2call_ring_duration": 21572,
        "total_dialer_connects": 87,
        "total_manual_attempts": 4,
        "total_manual_connects": 3,
        "walkin_count": 0,
        "psd_count": 1,
        "fsd_count": 1,
    },
    {
        "date": "2026-05-07",
        "login_duration": 30924,
        "dialer_talktime_duration": 15765,
        "click2call_talktime_duration": 0,
        "break_duration": 690,
        "dispose_duration": 8655,
        "click2call_ring_duration": 8682,
        "total_dialer_connects": 63,
        "total_manual_attempts": 9,
        "total_manual_connects": 6,
        "walkin_count": 1,
        "psd_count": 2,
        "fsd_count": 1,
    },
    {
        "date": "2026-05-05",
        "login_duration": 34035,
        "dialer_talktime_duration": 16071,
        "click2call_talktime_duration": 0,
        "break_duration": 470,
        "dispose_duration": 8831,
        "click2call_ring_duration": 1653,
        "total_dialer_connects": 70,
        "total_manual_attempts": 6,
        "total_manual_connects": 4,
        "walkin_count": 2,
        "psd_count": 1,
        "fsd_count": 1,
    },
    {
        "date": "2026-05-04",
        "login_duration": 35008,
        "dialer_talktime_duration": 20622,
        "click2call_talktime_duration": 0,
        "break_duration": 790,
        "dispose_duration": 6182,
        "click2call_ring_duration": 13419,
        "total_dialer_connects": 107,
        "total_manual_attempts": 5,
        "total_manual_connects": 3,
        "walkin_count": 0,
        "psd_count": 0,
        "fsd_count": 0,
    },
]

MOCK_AGENT_PERFORMANCE_DOCS: list[dict] = []
for date_idx, base in enumerate(BASE_DOCS_BY_DATE):
    for agent_idx, agent in enumerate(MOCK_AGENTS):
        factor = 0.85 + agent_idx * 0.08 + (date_idx % 3) * 0.03
        dialer_connects = max(1, round(base["total_dialer_connects"] * factor))
        c2c_attempts = max(0, round(base.get("total_click2call_attempts", base["total_manual_attempts"]) * factor))
        c2c_connects = max(0, round(base.get("total_click2call_connects", base["total_manual_connects"]) * factor))
        unique_connects = max(1, round(c2c_connects * 0.94))
        unique_attempts = max(1, round((dialer_connects + c2c_attempts) * 0.92))
        unique_interests = max(0, round(unique_connects * 0.12))
        unique_schedules_walkin = max(0, round(unique_connects * 0.05))
        MOCK_AGENT_PERFORMANCE_DOCS.append(
            {
                **base,
                "agent_id": agent["id"],
                "agent_name": agent["name"],
                "city": agent["city"],
                "login_duration": round(base["login_duration"] * factor),
                "dialer_session_duration": round(
                    base.get("dialer_session_duration", base["login_duration"] * 0.6) * factor
                ),
                "dialer_talktime_duration": round(base["dialer_talktime_duration"] * factor),
                "click2call_talktime_duration": round(base.get("click2call_talktime_duration", 0) * factor),
                "break_duration": round(base["break_duration"] * factor),
                "break_count": max(1, round(3 + agent_idx + date_idx % 2)),
                "dispose_duration": round(base["dispose_duration"] * factor),
                "click2call_ring_time": round(
                    base.get("click2call_ring_time", base.get("click2call_ring_duration", 0)) * factor
                ),
                "dialer_session_count": max(1, round(2 + agent_idx)),
                "total_dialer_connects": dialer_connects,
                "total_click2call_attempts": c2c_attempts,
                "total_click2call_connects": c2c_connects,
                "total_unique_attempts": unique_attempts,
                "total_unique_connects": unique_connects,
                "total_unique_interests": unique_interests,
                "unique_schedules_walkin": unique_schedules_walkin,
                "schedules_followup": max(0, round(4 + date_idx % 3)),
                "scheduled_followup": max(0, round(3 + agent_idx)),
                "completed_scheduled_followup": max(0, round(2 + date_idx % 2)),
                "new_walkin_schedules": max(0, round(base.get("walkin_count", 0) + 1)),
                "scheduled_walkin": max(0, round(2 + agent_idx)),
                "completed_scheduled_walkin": max(0, round(1 + date_idx % 2)),
                "walkin_count": max(0, round(base["walkin_count"] * factor)),
                "psd_count": max(0, round(base["psd_count"] * factor)),
                "fsd_count": max(0, round(base["fsd_count"] * factor)),
            }
        )


def _format_duration(seconds: int | float | None) -> str:
    s = max(0, int(seconds or 0))
    h, rem = divmod(s, 3600)
    m, sec = divmod(rem, 60)
    return f"{h:02d}:{m:02d}:{sec:02d}"


def _format_date_label(iso_date: str) -> str:
    y, m, d = iso_date.split("-")
    return f"{d}-{m}-{y}"


def _parse_iso_date(iso_date: str) -> datetime:
    return datetime.strptime(str(iso_date)[:10], "%Y-%m-%d")


def _normalize_granularity(granularity: str) -> str:
    g = (granularity or "day_wise").strip().lower().replace(" ", "_")
    if g in ("day", "day_wise", "daily"):
        return "day_wise"
    if g in ("week", "week_wise", "weekly"):
        return "week_wise"
    if g in ("month", "month_wise", "monthly"):
        return "month_wise"
    return "day_wise"


def _parse_agent_ids(agent_ids) -> list[str]:
    if not agent_ids:
        return []
    if isinstance(agent_ids, (list, tuple)):
        return [str(a).strip() for a in agent_ids if str(a).strip()]
    if isinstance(agent_ids, str):
        raw = agent_ids.strip()
        if not raw:
            return []
        try:
            parsed = json.loads(raw)
            if isinstance(parsed, list):
                return [str(a).strip() for a in parsed if str(a).strip()]
        except json.JSONDecodeError:
            pass
        return [a.strip() for a in raw.split(",") if a.strip()]
    return []


def _is_empty_metric_value(value, fmt: str) -> bool:
    """True when the cell should show '—' and must not open breakup."""
    if value is None or value == "":
        return True
    if fmt == "number":
        return int(flt(value) or 0) == 0
    if fmt == "duration":
        return _duration_to_seconds(value) == 0
    if fmt == "duration_with_count":
        if isinstance(value, (list, tuple)) and len(value) >= 2:
            return int(value[1] or 0) == 0
        return _duration_to_seconds(value) == 0
    if fmt == "percent":
        return float(value or 0) == 0
    if fmt == "ratio":
        if isinstance(value, (list, tuple)) and len(value) == 2:
            return int(value[0] or 0) == 0 and int(value[1] or 0) == 0
        return False
    if fmt == "text":
        return not str(value).strip()
    return str(value).strip() in ("0", "0.0", "00:00:00")


def _format_cell_value(value, fmt: str) -> str:
    if _is_empty_metric_value(value, fmt):
        return "—"
    if fmt == "duration":
        return _format_duration(value)
    if fmt == "duration_with_count":
        if isinstance(value, (list, tuple)) and len(value) >= 2:
            duration_sec, count = value[0], value[1]
            return f"{_format_duration(duration_sec)} ({int(count or 0)})"
        return _format_duration(value)
    if fmt == "percent":
        n = float(value)
        rounded = round(n * 10) / 10
        text = f"{int(rounded)}" if rounded % 1 == 0 else f"{rounded:.1f}"
        return f"{text}%"
    if fmt == "ratio":
        if isinstance(value, (list, tuple)) and len(value) == 2:
            return f"{value[0]}/{value[1]}"
        return str(value)
    return str(value)


def _ratio_pair(doc: dict, num_key: str, den_key: str) -> tuple[int, int]:
    return (_int_field(doc, num_key), _int_field(doc, den_key))


def _bucket_key(iso_date: str, granularity: str) -> str:
    dt = _parse_iso_date(iso_date)
    if granularity == "week_wise":
        week_start = dt - timedelta(days=dt.weekday())
        return week_start.strftime("%Y-%m-%d")
    if granularity == "month_wise":
        return dt.strftime("%Y-%m")
    return iso_date


def _format_bucket_label(bucket_key: str, granularity: str) -> str:
    if granularity == "day_wise":
        return _format_date_label(bucket_key)
    if granularity == "week_wise":
        start = _parse_iso_date(bucket_key)
        end = start + timedelta(days=6)
        return f"{start.strftime('%d-%m')} – {end.strftime('%d-%m-%Y')}"
    if granularity == "month_wise":
        y, m = bucket_key.split("-")
        month_label = month_name[int(m)]
        return f"{month_label} {y}"
    return bucket_key


_DURATION_AVG_KEYS = (
    "login_duration",
    "dialer_session_duration",
    "dialer_talktime_duration",
    "click2call_talktime_duration",
    "break_duration",
    "dispose_duration",
    "click2call_ring_time",
)

_COUNT_SUM_KEYS = (
    "total_dialer_connects",
    "total_click2call_attempts",
    "total_click2call_connects",
    "total_unique_attempts",
    "total_unique_connects",
    "total_unique_interests",
    "unique_schedules_walkin",
    "schedules_followup",
    "scheduled_followup",
    "completed_scheduled_followup",
    "new_walkin_schedules",
    "scheduled_walkin",
    "completed_scheduled_walkin",
    "psd_count",
    "fsd_count",
    "walkin_count",
)

_COUNT_AVG_KEYS = ("dialer_session_count", "break_count")


def _merge_docs(docs: list[dict]) -> dict:
    if not docs:
        return {}
    if len(docs) == 1:
        return dict(docs[0])

    merged = dict(docs[0])
    count = len(docs)
    for doc in docs[1:]:
        for key in _DURATION_AVG_KEYS:
            merged[key] = merged.get(key, 0) + doc.get(key, 0)
        for key in _COUNT_SUM_KEYS:
            merged[key] = merged.get(key, 0) + doc.get(key, 0)
        for key in _COUNT_AVG_KEYS:
            merged[key] = merged.get(key, 0) + doc.get(key, 0)

    for key in _DURATION_AVG_KEYS:
        merged[key] = round(merged.get(key, 0) / count)
    for key in _COUNT_AVG_KEYS:
        merged[key] = round(merged.get(key, 0) / count)
    return merged


def _bucket_agent_docs(agent_docs: list[dict], granularity: str) -> list[tuple[str, dict]]:
    buckets: dict[str, list[dict]] = {}
    for doc in agent_docs:
        key = _bucket_key(doc["date"], granularity)
        buckets.setdefault(key, []).append(doc)

    result = []
    for key in sorted(buckets.keys(), reverse=True):
        merged = _merge_docs(buckets[key])
        if merged:
            merged["agent_id"] = agent_docs[0].get("agent_id")
            merged["agent_name"] = agent_docs[0].get("agent_name")
            merged["city"] = agent_docs[0].get("city")
            result.append((key, merged))
    return result


def _talktime_seconds(d: dict) -> int:
    return (d.get("dialer_talktime_duration") or 0) + (d.get("click2call_talktime_duration") or 0)


def _total_connects(d: dict) -> int:
    return (d.get("total_dialer_connects") or 0) + (d.get("total_click2call_connects") or 0)


def _total_attempts(d: dict) -> int:
    return (d.get("total_dialer_connects") or 0) + (d.get("total_click2call_attempts") or 0)


def _interest_pct(d: dict) -> float:
    interests = d.get("total_unique_interests") or 0
    connects = d.get("total_unique_connects") or 0
    if not connects:
        return 0.0
    return (interests / connects) * 100


def _schedules_walkin_pct(d: dict) -> float:
    walkins = d.get("unique_schedules_walkin") or 0
    interests = d.get("total_unique_interests") or 0
    if not interests:
        return 0.0
    return (walkins / interests) * 100


def _interest_to_psd_pct(d: dict) -> float:
    psd = d.get("psd_count") or 0
    interests = d.get("total_unique_interests") or 0
    if not interests:
        return 0.0
    return (psd / interests) * 100


_STATS_BREAKUP_METRICS = frozenset(
    {
        "break_duration",
        "dialer_session_duration",
    }
)

_STATS_BREAKUP_COLUMNS = [
    {"key": "label", "label": "Statistic"},
    {"key": "value", "label": "Value"},
]


def _metric_definitions():
    return [
        {
            "metric_name": "login_duration",
            "label": "Avg daily login",
            "definition": "Average time per day the agent was logged in, based on CRM heartbeat.",
            "group": "time_metrics",
            "format": "duration",
            "get_value": lambda d: d.get("login_duration"),
        },
        {
            "metric_name": "dialer_session_duration",
            "label": "Avg dialer session duration",
            "definition": "Average dialer session time per day. Parentheses show session count.",
            "group": "time_metrics",
            "format": "duration_with_count",
            "clickable": True,
            "get_value": lambda d: (
                d.get("dialer_session_duration") or 0,
                d.get("dialer_session_count") or 0,
            ),
        },
        {
            "metric_name": "talktime",
            "label": "Avg daily talktime",
            "definition": "Average daily call talk time (dialer plus agent calling combined).",
            "group": "time_metrics",
            "format": "duration",
            "get_value": _talktime_seconds,
        },
        {
            "metric_name": "break_duration",
            "label": "Avg daily pause",
            "definition": "Average daily dialer pause or break time. Parentheses show break count.",
            "group": "time_metrics",
            "format": "duration_with_count",
            "clickable": True,
            "get_value": lambda d: (
                d.get("break_duration") or 0,
                d.get("break_count") or 0,
            ),
        },
        {
            "metric_name": "click2call_ring_time",
            "label": "Avg daily ring",
            "definition": "Average daily ring time for agent calling attempts before connect.",
            "group": "time_metrics",
            "format": "duration",
            "get_value": lambda d: d.get("click2call_ring_time"),
        },
        {
            "metric_name": "dispose_duration",
            "label": "Avg daily dispo",
            "definition": "Average daily after-call wrap-up (dispose) time.",
            "group": "time_metrics",
            "format": "duration",
            "get_value": lambda d: d.get("dispose_duration"),
        },
        {
            "metric_name": "aht",
            "label": "Avg AHT",
            "definition": "Average Handle Time: total talk time divided by total connects.",
            "group": "time_metrics",
            "format": "duration",
            "section_end": True,
            "get_value": lambda d: (
                round(_talktime_seconds(d) / _total_connects(d)) if _total_connects(d) else 0
            ),
        },
        {
            "metric_name": "total_attempts",
            "label": "Total attempts",
            "definition": "Dialer connects plus agent calling attempts.",
            "group": "attempt_metrics",
            "format": "number",
            "section_start": True,
            "clickable": True,
            "get_value": _total_attempts,
        },
        {
            "metric_name": "unique_attempts",
            "label": "Unique attempts",
            "definition": "Count of distinct phone numbers attempted.",
            "group": "attempt_metrics",
            "format": "number",
            "get_value": lambda d: d.get("total_unique_attempts") or 0,
        },
        {
            "metric_name": "total_connects",
            "label": "Total connects",
            "definition": "Dialer connects plus agent calling connects.",
            "group": "attempt_metrics",
            "format": "number",
            "clickable": True,
            "get_value": _total_connects,
        },
        {
            "metric_name": "unique_connects",
            "label": "Unique connects",
            "definition": "Count of distinct phone numbers with a successful connect.",
            "group": "attempt_metrics",
            "format": "number",
            "get_value": lambda d: d.get("total_unique_connects") or 0,
        },
        {
            "metric_name": "unique_interests",
            "label": "Unique interests",
            "definition": "Count of distinct leads marked as interested.",
            "group": "conversion_metrics",
            "format": "number",
            "get_value": lambda d: d.get("total_unique_interests") or 0,
        },
        {
            "metric_name": "interest_pct",
            "label": "Interest %",
            "definition": "Unique interests as a percentage of unique connects.",
            "group": "conversion_metrics",
            "format": "percent",
            "get_value": _interest_pct,
        },
        {
            "metric_name": "unique_schedules_walkin",
            "label": "Unique schedules walkin",
            "definition": "Count of unique walk-in visit schedules created.",
            "group": "conversion_metrics",
            "format": "number",
            "get_value": lambda d: d.get("unique_schedules_walkin") or 0,
        },
        {
            "metric_name": "schedules_walkin_pct",
            "label": "Schedules walkin %",
            "definition": "Unique walk-in schedules as a percentage of unique interests.",
            "group": "conversion_metrics",
            "format": "percent",
            "section_end": True,
            "get_value": _schedules_walkin_pct,
        },
        {
            "metric_name": "schedules_followup",
            "label": "New followup schedules",
            "definition": "New follow-up schedules created in the selected period.",
            "group": "schedule_metrics",
            "format": "number",
            "section_start": True,
            "clickable": True,
            "get_value": lambda d: d.get("schedules_followup") or 0,
        },
        {
            "metric_name": "followup_done",
            "label": "Followup done",
            "definition": "Completed scheduled follow-ups over total scheduled follow-ups.",
            "group": "schedule_metrics",
            "format": "ratio",
            "clickable": True,
            "get_value": lambda d: _ratio_pair(
                d, "completed_scheduled_followup", "scheduled_followup"
            ),
        },
        {
            "metric_name": "new_walkin_schedules",
            "label": "New walkin schedules",
            "definition": "New walk-in visit schedules created in the selected period.",
            "group": "schedule_metrics",
            "format": "number",
            "clickable": True,
            "get_value": lambda d: d.get("new_walkin_schedules") or 0,
        },
        {
            "metric_name": "walkin_done",
            "label": "Walkin done",
            "definition": "Completed scheduled walk-ins over total scheduled walk-ins.",
            "group": "schedule_metrics",
            "format": "ratio",
            "clickable": True,
            "get_value": lambda d: _ratio_pair(
                d, "completed_scheduled_walkin", "scheduled_walkin"
            ),
        },
        {
            "metric_name": "psd_count",
            "label": "PSD count",
            "definition": "Leads with PSD (payment schedule document) received in the selected period.",
            "group": "psd_metrics",
            "format": "number",
            "section_start": True,
            "get_value": lambda d: d.get("psd_count") or 0,
        },
        {
            "metric_name": "fsd_count",
            "label": "FSD count",
            "definition": "Leads with FSD (full schedule document) received in the selected period.",
            "group": "psd_metrics",
            "format": "number",
            "get_value": lambda d: d.get("fsd_count") or 0,
        },
        {
            "metric_name": "interest_to_psd_pct",
            "label": "Interest to PSD %",
            "definition": "PSD count as a percentage of unique interests.",
            "group": "psd_metrics",
            "format": "percent",
            "section_start": True,
            "get_value": _interest_to_psd_pct,
        },
    ]


def build_analytics_payload(
    docs: list[dict],
    agents: list[dict],
    granularity: str,
) -> dict:
    granularity = _normalize_granularity(granularity)
    columns: list[dict] = []
    column_docs: list[dict] = []

    for agent in agents:
        agent_docs = [d for d in docs if d.get("agent_id") == agent["id"]]
        for bucket_key, bucket_doc in _bucket_agent_docs(agent_docs, granularity):
            col_id = f"{agent['id']}__{bucket_key}"
            columns.append(
                {
                    "id": col_id,
                    "agent_id": agent["id"],
                    "agent_name": agent["name"],
                    "period_key": bucket_key,
                    "period_label": _format_bucket_label(bucket_key, granularity),
                }
            )
            column_docs.append(bucket_doc)

    show_agent_header = len(agents) != 1

    rows = []
    col_count = len(column_docs)
    for definition in _metric_definitions():
        metric_name = definition["metric_name"]
        fmt = definition["format"]
        clickable = bool(definition.get("clickable")) or metric_name in CLICKABLE_METRICS
        raw_values = [definition["get_value"](doc) for doc in column_docs]
        clickable_cells = [
            clickable and not _is_empty_metric_value(raw, fmt) for raw in raw_values
        ]
        rows.append(
            {
                "metric_name": metric_name,
                "label": definition["label"],
                "definition": definition.get("definition") or "",
                "group": definition["group"],
                "format": fmt,
                "row_type": "metric",
                "section_start": bool(definition.get("section_start")),
                "section_end": bool(definition.get("section_end")),
                "clickable": clickable,
                "clickable_cells": clickable_cells,
                "values": [_format_cell_value(raw, fmt) for raw in raw_values],
            }
        )

    dates = [c["period_label"] for c in columns]
    return {
        "columns": columns,
        "dates": dates,
        "rows": rows,
        "show_agent_header": show_agent_header,
        "granularity": granularity,
    }


def _period_key_date_span(period_key: str, granularity: str) -> tuple[datetime.date, datetime.date]:
    """Inclusive date range for filtering mock pause rows to a dashboard column bucket."""
    granularity = _normalize_granularity(granularity)
    pk = str(period_key).strip()
    if granularity == "month_wise":
        y, mo = pk.split("-")[:2]
        year, month = int(y), int(mo)
        start = datetime(year, month, 1).date()
        if month == 12:
            end = datetime(year, 12, 31).date()
        else:
            end = (datetime(year, month + 1, 1) - timedelta(days=1)).date()
        return start, end
    if granularity == "week_wise":
        start = datetime.strptime(pk[:10], "%Y-%m-%d").date()
        end = start + timedelta(days=6)
        return start, end
    start = datetime.strptime(pk[:10], "%Y-%m-%d").date()
    return start, start


def _resolve_breakup_date_span(
    *,
    from_date: str | None,
    to_date: str | None,
    period_key: str | None,
    granularity: str,
) -> tuple[str, str] | None:
    """Return inclusive ISO date bounds for breakup queries."""
    granularity = _normalize_granularity(granularity)
    if period_key:
        try:
            span_start, span_end = _period_key_date_span(period_key, granularity)
            return span_start.isoformat(), span_end.isoformat()
        except ValueError:
            pass
    fd = (from_date or "").strip()[:10]
    td = (to_date or "").strip()[:10]
    if fd and td:
        return fd, td
    if fd:
        return fd, fd
    return None


def _breakup_datetime_bounds(from_date: str, to_date: str) -> tuple[str, str]:
    return f"{from_date} 00:00:00", f"{to_date} 23:59:59.999999"


def _valid_doctype_fields(doctype: str, fieldnames: list[str]) -> list[str]:
    if not frappe.db.exists("DocType", doctype):
        return []
    valid = set(frappe.get_meta(doctype).get_valid_columns())
    out = ["name"]
    for f in fieldnames:
        if f in valid and f not in out:
            out.append(f)
    return out


def _call_session_connected_field() -> str:
    if frappe.db.has_column(CALL_SESSION_DOCTYPE, "connected_at"):
        return "connected_at"
    return "lead_answered_at"


def _call_session_breakup_fields() -> list[str]:
    connected = _call_session_connected_field()
    return [
        "calling_method",
        "direction",
        "lead",
        "status",
        "duration",
        "disposition_status",
        "sub_disposition_status",
        "disposition_remarks",
        "creation",
        connected,
    ]


def _fetch_call_sessions_breakup(
    agent_ids: list[str],
    from_date: str,
    to_date: str,
    *,
    mode: str,
) -> list[dict]:
    """Load Call Session rows for total_attempts / total_connects breakup."""
    if not agent_ids or not frappe.db.exists("DocType", CALL_SESSION_DOCTYPE):
        return []

    from frappe.query_builder import DocType
    from frappe.query_builder.functions import Coalesce

    connected_field = _call_session_connected_field()
    start_dt, end_dt = _breakup_datetime_bounds(from_date, to_date)
    fieldnames = _call_session_breakup_fields()
    fetch_fields = _valid_doctype_fields(CALL_SESSION_DOCTYPE, fieldnames)
    if not fetch_fields:
        return []

    CS = DocType(CALL_SESSION_DOCTYPE)
    connected_col = getattr(CS, connected_field, None)
    if connected_col is None:
        return []

    select_cols = [CS.name]
    for f in fetch_fields:
        if f == "name":
            continue
        col = getattr(CS, f, None)
        if col is not None:
            select_cols.append(col)

    date_expr = Coalesce(connected_col, CS.creation)

    def _run_query(extra_filters: list) -> list:
        q = (
            frappe.qb.from_(CS)
            .select(*select_cols)
            .where(CS.agent.isin(agent_ids))
            .where(date_expr >= start_dt)
            .where(date_expr <= end_dt)
        )
        for cond in extra_filters:
            q = q.where(cond)
        return q.orderby(date_expr, order=frappe.qb.desc).run(as_dict=True)

    raw_rows: list[dict] = []
    if mode == "attempts":
        dialer_rows = _run_query(
            [
                CS.calling_method == "Dialer",
                connected_col.isnotnull(),
            ]
        )
        c2c_rows = _run_query([CS.calling_method == EnumValues.CallingMethod.Agent])
        by_name = {r["name"]: r for r in dialer_rows + c2c_rows}
        raw_rows = list(by_name.values())
    elif mode == "connects":
        raw_rows = _run_query([connected_col.isnotnull()])
    else:
        return []

    raw_rows.sort(
        key=lambda r: str(r.get(connected_field) or r.get("creation") or ""),
        reverse=True,
    )

    out = []
    for row in raw_rows:
        serialized = _serialize_breakup_row(row, fetch_fields)
        date_raw = serialized.get(connected_field) or serialized.get("creation") or ""
        out.append(
            {
                "date": date_raw,
                "direction": serialized.get("direction") or "",
                "lead_id": serialized.get("lead") or "",
                "status": serialized.get("status") or "",
                "duration": _format_duration(_duration_to_seconds(serialized.get("duration"))),
                "primary_status": serialized.get("disposition_status") or "",
                "secondary_status": serialized.get("sub_disposition_status") or "",
                "disposition_remarks": serialized.get("disposition_remarks") or "",
            }
        )
    return out


def _event_visit_date_sql_expr(alias: str = "e") -> str:
    cols = frappe.db.get_table_columns(EVENT_DOCTYPE) or []
    if "call_at" in cols:
        return f"DATE(COALESCE({alias}.`call_at`, {alias}.`starts_on`))"
    return f"DATE({alias}.`starts_on`)"


def _event_breakup_fieldnames() -> list[str]:
    candidates = [
        "name",
        "owner",
        "creation",
        "event_category",
        "call_at",
        "starts_on",
        "callback_status",
        "event_day_dial_count",
        "reference_docname",
        "reference_doctype",
        "subject",
        "preferred_scheme",
        "disposition_status",
        "sub_disposition_status",
        "disposition_remarks",
    ]
    cols = set(frappe.db.get_table_columns(EVENT_DOCTYPE) or [])
    return [f for f in candidates if f in cols]


def _format_event_breakup_datetime(val) -> str:
    if val is None or val == "":
        return ""
    if isinstance(val, datetime):
        return val.strftime("%Y-%m-%d %H:%M:%S")
    if hasattr(val, "strftime"):
        return val.strftime("%Y-%m-%d %H:%M:%S")
    return str(val)


def _event_row_to_breakup(row: dict) -> dict:
    visit_raw = row.get("call_at") or row.get("starts_on") or ""
    lead_id = ""
    if (row.get("reference_doctype") or "") == EnumValues.ReferenceDocType.CRM_LEAD:
        lead_id = (row.get("reference_docname") or "").strip()
    return {
        "id": row.get("name") or "",
        "created_at": _format_event_breakup_datetime(row.get("creation")),
        "visit_date": _format_event_breakup_datetime(visit_raw),
        "lead_id": lead_id,
        "callback_status": row.get("callback_status") or "",
        "preferred_scheme": row.get("preferred_scheme") or "",
        "event_day_dial_count": row.get("event_day_dial_count") or 0,
        "last_7_day_dial_count": 0,
        "owner": row.get("owner") or "",
        "subject": row.get("subject") or "",
        "primary_status": row.get("disposition_status") or "",
        "secondary_status": row.get("sub_disposition_status") or "",
        "disposition_remarks": row.get("disposition_remarks") or "",
    }


def _enrich_event_breakup_rows(rows: list[dict]) -> list[dict]:
    lead_ids = list(dict.fromkeys([r.get("lead_id") for r in rows if r.get("lead_id")]))
    if lead_ids and frappe.db.exists("DocType", "CRM Lead"):
        lead_cols = set(frappe.db.get_table_columns("CRM Lead") or [])
        fields = ["name"]
        if "preferred_scheme" in lead_cols:
            fields.append("preferred_scheme")
        if "last_7_day_dial_count" in lead_cols:
            fields.append("last_7_day_dial_count")
        lead_rows = frappe.get_all(
            "CRM Lead",
            filters={"name": ("in", lead_ids)},
            fields=fields,
            limit_page_length=0,
        )
        lead_map = {r.name: r for r in (lead_rows or [])}
        for row in rows:
            lead = lead_map.get(row.get("lead_id") or "")
            if not lead:
                continue
            if not row.get("preferred_scheme"):
                row["preferred_scheme"] = lead.get("preferred_scheme") or ""
            row["last_7_day_dial_count"] = int(lead.get("last_7_day_dial_count") or 0)

    name_map = _user_display_name_map([row.get("owner") for row in rows])
    for row in rows:
        row["owner"] = name_map.get(row.get("owner") or "", row.get("owner") or "")
    return rows


def _fetch_events_breakup(
    agent_ids: list[str],
    from_date: str,
    to_date: str,
    *,
    mode: str,
) -> list[dict]:
    """Load Event rows for follow-up / walk-in schedule metric breakups."""
    if not agent_ids or not frappe.db.exists("DocType", EVENT_DOCTYPE):
        return []

    fieldnames = _event_breakup_fieldnames()
    if not fieldnames:
        return []

    start_dt, end_dt = _breakup_datetime_bounds(from_date, to_date)
    visit_date_x = _event_visit_date_sql_expr("e")
    select_sql = ", ".join(f"e.`{f}`" for f in fieldnames)

    conditions = ["e.`owner` IN %(owners)s"]
    params: dict = {"owners": tuple(agent_ids)}

    if mode == "schedules_followup":
        conditions.extend(
            [
                "e.`event_category` = %(callback_cat)s",
                "e.`creation` >= %(start_dt)s",
                "e.`creation` <= %(end_dt)s",
            ]
        )
        params["callback_cat"] = EnumValues.EventCallbackCategory.CALLBACK
        params["start_dt"] = start_dt
        params["end_dt"] = end_dt
    elif mode == "followup_done":
        conditions.extend(
            [
                "e.`event_category` = %(callback_cat)s",
                f"{visit_date_x} >= %(from_day)s",
                f"{visit_date_x} <= %(to_day)s",
            ]
        )
        params["callback_cat"] = EnumValues.EventCallbackCategory.CALLBACK
        params["from_day"] = getdate(from_date)
        params["to_day"] = getdate(to_date)
    elif mode == "new_walkin_schedules":
        conditions.extend(
            [
                "e.`event_category` = %(visit_cat)s",
                "e.`creation` >= %(start_dt)s",
                "e.`creation` <= %(end_dt)s",
                "IFNULL(e.`callback_status`, '') != %(override_status)s",
            ]
        )
        params["visit_cat"] = EnumValues.EventCallbackCategory.VISIT_DATE
        params["start_dt"] = start_dt
        params["end_dt"] = end_dt
        params["override_status"] = EnumValues.EventCallbackStatus.OVERRIDE
    elif mode == "walkin_done":
        conditions.extend(
            [
                "e.`event_category` = %(visit_cat)s",
                f"{visit_date_x} >= %(from_day)s",
                f"{visit_date_x} <= %(to_day)s",
                "IFNULL(e.`callback_status`, '') != %(override_status)s",
            ]
        )
        params["visit_cat"] = EnumValues.EventCallbackCategory.VISIT_DATE
        params["from_day"] = getdate(from_date)
        params["to_day"] = getdate(to_date)
        params["override_status"] = EnumValues.EventCallbackStatus.OVERRIDE
    else:
        return []

    rows = frappe.db.sql(
        f"""
        SELECT {select_sql}
        FROM `tabEvent` e
        WHERE {" AND ".join(conditions)}
        ORDER BY e.`creation` DESC, e.`name` DESC
        """,
        params,
        as_dict=True,
    )
    return _enrich_event_breakup_rows([_event_row_to_breakup(r) for r in (rows or [])])


def _serialize_breakup_row(row, fields: list[str]) -> dict:
    data = {}
    for f in fields:
        val = getattr(row, f, None)
        if val is None:
            data[f] = ""
        elif isinstance(val, datetime):
            data[f] = val.strftime("%Y-%m-%d %H:%M:%S")
        elif hasattr(val, "date") and hasattr(val, "strftime"):
            data[f] = val.strftime("%Y-%m-%d %H:%M:%S")
        else:
            data[f] = str(val)
    return data


def _fetch_logs_overlapping_period(
    doctype: str,
    *,
    agent_ids: list[str],
    from_date: str,
    to_date: str,
    start_field: str,
    end_field: str,
    fields: list[str],
    order_by: str,
) -> list:
    """Rows overlapping [from_date, to_date] (same pattern as agent_performance service)."""
    if not agent_ids or not frappe.db.exists("DocType", doctype):
        return []

    fetch_fields = _valid_doctype_fields(doctype, fields)
    if not fetch_fields:
        return []

    start_dt, end_dt = _breakup_datetime_bounds(from_date, to_date)
    user_filter = {"user": ("in", agent_ids)}

    started_in_period = frappe.get_all(
        doctype,
        filters={**user_filter, start_field: ("between", [start_dt, end_dt])},
        fields=fetch_fields,
        limit_page_length=0,
    )

    still_open = frappe.get_all(
        doctype,
        filters={
            **user_filter,
            start_field: ("<", start_dt),
            end_field: ("is", "not set"),
        },
        fields=fetch_fields,
        limit_page_length=0,
    )

    ended_in_period = frappe.get_all(
        doctype,
        filters={
            **user_filter,
            start_field: ("<", start_dt),
            end_field: ("between", [start_dt, end_dt]),
        },
        fields=fetch_fields,
        limit_page_length=0,
    )

    by_name: dict[str, object] = {}
    for row in started_in_period + still_open + ended_in_period:
        by_name[row.name] = row

    rows = list(by_name.values())
    if order_by:
        rows.sort(key=lambda r: getattr(r, start_field, None) or "", reverse=True)
    return rows


def _user_display_name_map(user_ids: list[str]) -> dict[str, str]:
    ids = list({u for u in user_ids if u})
    if not ids:
        return {}
    rows = frappe.get_all(
        "User",
        filters={"name": ("in", ids)},
        fields=["name", "full_name"],
        limit_page_length=0,
    )
    return {r.name: ((r.full_name or "").strip() or r.name) for r in (rows or [])}


def _fetch_break_logs_from_db(agent_ids: list[str], from_date: str, to_date: str) -> list[dict]:
    doctype = "User dialer session break logs"
    fieldnames = ["break_name", "start_time", "end_time", "user"]
    fetch_fields = _valid_doctype_fields(doctype, fieldnames)
    raw = _fetch_logs_overlapping_period(
        doctype,
        agent_ids=agent_ids,
        from_date=from_date,
        to_date=to_date,
        start_field="start_time",
        end_field="end_time",
        fields=fieldnames,
        order_by="start_time desc",
    )
    serialized = [_serialize_breakup_row(r, fetch_fields) for r in raw]
    name_map = _user_display_name_map([row.get("user") for row in serialized])
    return [
        {
            "id": row.get("name") or "",
            "user": name_map.get(row.get("user") or "", row.get("user") or ""),
            "break_name": row.get("break_name") or "",
            "start_time": row.get("start_time") or "",
            "end_time": row.get("end_time") or "",
        }
        for row in serialized
    ]


def _fetch_dialer_sessions_from_db(agent_ids: list[str], from_date: str, to_date: str) -> list[dict]:
    doctype = "User dialer session logs"
    fieldnames = [
        "user",
        "campaign_id",
        "campaign_name",
        "active_at",
        "inactive_at",
        "inactive_reason",
    ]
    fetch_fields = _valid_doctype_fields(doctype, fieldnames)
    raw = _fetch_logs_overlapping_period(
        doctype,
        agent_ids=agent_ids,
        from_date=from_date,
        to_date=to_date,
        start_field="active_at",
        end_field="inactive_at",
        fields=fieldnames,
        order_by="active_at desc",
    )
    serialized = [_serialize_breakup_row(r, fetch_fields) for r in raw]
    name_map = _user_display_name_map([row.get("user") for row in serialized])
    rows = []
    for row in serialized:
        campaign = (row.get("campaign_name") or row.get("campaign_id") or "").strip()
        rows.append(
            {
                "id": row.get("name") or "",
                "user": name_map.get(row.get("user") or "", row.get("user") or ""),
                "campaign": campaign,
                "active_at": row.get("active_at") or "",
                "inactive_at": row.get("inactive_at") or "",
                "inactive_reason": row.get("inactive_reason") or "",
            }
        )
    return rows


def _mock_breakup_rows(
    metric_name: str,
    agent_ids: list[str],
    from_date: str,
    to_date: str,
) -> list[dict]:
    seed = int(
        hashlib.md5(f"{metric_name}:{','.join(agent_ids)}:{from_date}:{to_date}".encode()).hexdigest()[
            :12
        ],
        16,
    )
    rnd = random.Random(seed)
    agent_id = agent_ids[0] if agent_ids else ""
    alias = (agent_id.split("@")[0] or "AGT")[:6].upper()
    n = rnd.randint(2, 6)
    rows = []
    for i in range(n):
        if metric_name == "break_count":
            start_dt = datetime.strptime(from_date, "%Y-%m-%d") + timedelta(
                hours=rnd.randint(9, 17), minutes=rnd.randint(0, 55)
            )
            end_dt = start_dt + timedelta(minutes=rnd.randint(3, 25))
            rows.append(
                {
                    "name": f"BREAK-{alias}-{i}",
                    "start_time": start_dt.strftime("%Y-%m-%d %H:%M:%S"),
                    "end_time": end_dt.strftime("%Y-%m-%d %H:%M:%S"),
                    "user": agent_id,
                    "user_dialer_session_log": f"DSL-{alias}-{i}",
                    "break_code": rnd.choice(["LUNCH", "BIO", "TEA"]),
                }
            )
        elif metric_name == "dialer_session_count":
            start_dt = datetime.strptime(from_date, "%Y-%m-%d") + timedelta(
                hours=rnd.randint(8, 16), minutes=rnd.randint(0, 55)
            )
            end_dt = start_dt + timedelta(hours=rnd.randint(1, 4))
            rows.append(
                {
                    "name": f"DSL-{alias}-{i}",
                    "user": agent_id,
                    "campaign_id": f"CAMP-{rnd.randint(100, 999)}",
                    "status": rnd.choice(["ACTIVE", "INACTIVE"]),
                    "active_at": start_dt.strftime("%Y-%m-%d %H:%M:%S"),
                    "inactive_at": end_dt.strftime("%Y-%m-%d %H:%M:%S"),
                }
            )
        else:
            rows.append(
                {
                    "name": f"ROW-{metric_name}-{alias}-{i}",
                    "agent": agent_id,
                    "date": from_date,
                    "detail": f"{metric_name} record {i + 1}",
                    "value": rnd.randint(1, 50),
                }
            )
    return rows


_BREAKUP_COLUMNS: dict[str, list[dict]] = {
    "break_duration": [
        {"key": "id", "label": "ID"},
        {"key": "user", "label": "User"},
        {"key": "break_name", "label": "Break name"},
        {"key": "start_time", "label": "Start time"},
        {"key": "end_time", "label": "End time"},
    ],
    "break_count": [
        {"key": "id", "label": "ID"},
        {"key": "user", "label": "User"},
        {"key": "break_name", "label": "Break name"},
        {"key": "start_time", "label": "Start time"},
        {"key": "end_time", "label": "End time"},
    ],
    "dialer_session_duration": [
        {"key": "id", "label": "ID"},
        {"key": "user", "label": "User"},
        {"key": "campaign", "label": "Campaign"},
        {"key": "active_at", "label": "Active at"},
        {"key": "inactive_at", "label": "Inactive at"},
        {"key": "inactive_reason", "label": "Inactive reason"},
    ],
    "dialer_session_count": [
        {"key": "id", "label": "ID"},
        {"key": "user", "label": "User"},
        {"key": "campaign", "label": "Campaign"},
        {"key": "active_at", "label": "Active at"},
        {"key": "inactive_at", "label": "Inactive at"},
        {"key": "inactive_reason", "label": "Inactive reason"},
    ],
    "total_attempts": [
        {
            "key": "lead_id",
            "label": "Lead Id",
            "link_route": "leads",
            "link_query": {"viewType": "list"},
            "link_hash": "activity",
            "link_plain": True,
        },
        {"key": "status", "label": "Call Status"},
        {"key": "direction", "label": "Direction"},
        {"key": "primary_status", "label": "Primary status"},
        {"key": "secondary_status", "label": "Secondary status"},
        {"key": "duration", "label": "Duration"},
        {"key": "disposition_remarks", "label": "Disposition remarks"},
    ],
    "total_connects": [
        {
            "key": "lead_id",
            "label": "Lead Id",
            "link_route": "leads",
            "link_query": {"viewType": "list"},
            "link_hash": "activity",
            "link_plain": True,
        },
        {"key": "status", "label": "Call Status"},
        {"key": "direction", "label": "Direction"},
        {"key": "primary_status", "label": "Primary status"},
        {"key": "secondary_status", "label": "Secondary status"},
        {"key": "duration", "label": "Duration"},
        {"key": "disposition_remarks", "label": "Disposition remarks"},
    ],
}

_EVENT_FOLLOWUP_BREAKUP_COLUMNS = [
    {
        "key": "lead_id",
        "label": "Lead Id",
        "link_route": "leads",
        "link_query": {"viewType": "list"},
        "link_hash": "activity",
        "link_plain": True,
    },
    {"key": "primary_status", "label": "Primary Status"},
    {"key": "visit_date", "label": "Next followup date"},
    {"key": "callback_status", "label": "Followup status"},
    {"key": "preferred_scheme", "label": "Preferred scheme"},
    {"key": "event_day_dial_count", "label": "Dial attempt"},
    {"key": "last_7_day_dial_count", "label": "7D attempts"},
    {"key": "owner", "label": "Owner"},
    {"key": "disposition_remarks", "label": "Remarks"},
]

_EVENT_BREAKUP_COLUMNS = [
    {
        "key": "lead_id",
        "label": "Lead Id",
        "link_route": "leads",
        "link_query": {"viewType": "list"},
        "link_hash": "activity",
        "link_plain": True,
    },
    {"key": "primary_status", "label": "Primary Status"},
    {"key": "visit_date", "label": "Next visit date"},
    {"key": "callback_status", "label": "Visit status"},
    {"key": "preferred_scheme", "label": "Preferred scheme"},
    {"key": "event_day_dial_count", "label": "Dial attempt"},
    {"key": "last_7_day_dial_count", "label": "7D attempts"},
    {"key": "owner", "label": "Owner"},
    {"key": "disposition_remarks", "label": "Remarks"},
]

_BREAKUP_COLUMNS["schedules_followup"] = list(_EVENT_FOLLOWUP_BREAKUP_COLUMNS)
_BREAKUP_COLUMNS["followup_done"] = list(_EVENT_FOLLOWUP_BREAKUP_COLUMNS)

for _event_metric in ("new_walkin_schedules", "walkin_done"):
    _BREAKUP_COLUMNS[_event_metric] = list(_EVENT_BREAKUP_COLUMNS)

_CALL_SESSION_BREAKUP_METRICS = frozenset({"total_attempts", "total_connects"})
_EVENT_BREAKUP_METRICS = frozenset(
    {"schedules_followup", "followup_done", "new_walkin_schedules", "walkin_done"}
)

_BREAKUP_NO_LINK_METRICS = frozenset(
    {"dialer_session_duration", "dialer_session_count", "break_duration", "break_count"}
)

_DEFAULT_BREAKUP_COLUMNS = [
    {"key": "date", "label": "Date"},
    {"key": "agent", "label": "Agent"},
    {"key": "detail", "label": "Detail"},
    {"key": "value", "label": "Value"},
]


def _breakup_columns_for_rows(metric_name: str, rows: list[dict]) -> list[dict]:
    """Return column defs for the drawer table."""
    base = _BREAKUP_COLUMNS.get(metric_name, _DEFAULT_BREAKUP_COLUMNS)
    if (
        metric_name in _BREAKUP_NO_LINK_METRICS
        or metric_name in _CALL_SESSION_BREAKUP_METRICS
        or metric_name in _EVENT_BREAKUP_METRICS
    ):
        return base
    if not rows:
        return base
    keys_with_data = set()
    for row in rows:
        for k, v in row.items():
            if v not in (None, ""):
                keys_with_data.add(k)
    filtered = [c for c in base if c["key"] in keys_with_data or c["key"] in ("name", "user")]
    return filtered or base


def _build_stats_breakup_rows(metric_name: str, docs: list[dict]) -> list[dict]:
    """Summary rows for averaged metrics (cell value vs underlying record totals)."""
    if not docs:
        return []

    day_count = len(docs)

    if metric_name == "break_duration":
        duration_key = "break_duration"
        count_key = "break_count"
        avg_duration_label = "Avg daily pause duration"
        avg_count_label = "Avg daily pause count (shown in table)"
        total_duration_label = "Total pause duration"
        total_count_label = "Total pause records"
    elif metric_name == "dialer_session_duration":
        duration_key = "dialer_session_duration"
        count_key = "dialer_session_count"
        avg_duration_label = "Avg dialer session duration"
        avg_count_label = "Avg sessions per day (shown in table)"
        total_duration_label = "Total dialer session duration"
        total_count_label = "Total dialer sessions"
    else:
        return []

    total_duration = sum(_duration_to_seconds(d.get(duration_key)) for d in docs)
    total_count = sum(_int_field(d, count_key) for d in docs)
    avg_duration = round(total_duration / day_count) if day_count else 0
    avg_count = round(total_count / day_count) if day_count else 0

    return [
        {"label": avg_duration_label, "value": _format_duration(avg_duration)},
        {"label": avg_count_label, "value": str(avg_count)},
        {"label": "Days in period", "value": str(day_count)},
        {"label": total_duration_label, "value": _format_duration(total_duration)},
        {"label": total_count_label, "value": str(total_count)},
    ]


def get_agent_performance_breakup(
    *,
    metric_name: str,
    agent_ids=None,
    from_date: str | None = None,
    to_date: str | None = None,
    granularity: str = "day_wise",
    period_key: str | None = None,
    city: str | None = None,
) -> dict:
    """
    Unified breakup for Agent Performance drawer.
    Body: metric_name, agent_ids[], from_date, to_date, granularity, optional period_key.
    """
    metric_name = (metric_name or "").strip()
    if not metric_name:
        return {"columns": [], "rows": []}

    parsed_ids = _parse_agent_ids(agent_ids)
    if not parsed_ids:
        return {"columns": _BREAKUP_COLUMNS.get(metric_name, _DEFAULT_BREAKUP_COLUMNS), "rows": []}

    span = _resolve_breakup_date_span(
        from_date=from_date,
        to_date=to_date,
        period_key=period_key,
        granularity=granularity,
    )
    if not span:
        return {"columns": _BREAKUP_COLUMNS.get(metric_name, _DEFAULT_BREAKUP_COLUMNS), "rows": []}

    fd, td = span
    rows: list[dict] = []

    if metric_name in _STATS_BREAKUP_METRICS:
        perf_docs = _fetch_performance_docs_from_db(
            from_date=fd,
            to_date=td,
            agent_ids=parsed_ids,
            hub_id=(city or "").strip(),
        )
        stats = _build_stats_breakup_rows(metric_name, perf_docs)
        if metric_name == "break_duration":
            detail_rows = _fetch_break_logs_from_db(parsed_ids, fd, td)
        else:
            detail_rows = _fetch_dialer_sessions_from_db(parsed_ids, fd, td)
        detail_columns = _breakup_columns_for_rows(metric_name, detail_rows)
        return {
            "view_mode": "hybrid",
            "stats": stats,
            "columns": detail_columns,
            "rows": detail_rows,
            "metric_name": metric_name,
            "linkable": metric_name not in _BREAKUP_NO_LINK_METRICS,
        }

    if metric_name == "break_count":
        rows = _fetch_break_logs_from_db(parsed_ids, fd, td)
    elif metric_name == "dialer_session_count":
        rows = _fetch_dialer_sessions_from_db(parsed_ids, fd, td)
    elif metric_name == "total_attempts":
        rows = _fetch_call_sessions_breakup(parsed_ids, fd, td, mode="attempts")
    elif metric_name == "total_connects":
        rows = _fetch_call_sessions_breakup(parsed_ids, fd, td, mode="connects")
    elif metric_name == "schedules_followup":
        rows = _fetch_events_breakup(parsed_ids, fd, td, mode="schedules_followup")
    elif metric_name == "followup_done":
        rows = _fetch_events_breakup(parsed_ids, fd, td, mode="followup_done")
    elif metric_name == "new_walkin_schedules":
        rows = _fetch_events_breakup(parsed_ids, fd, td, mode="new_walkin_schedules")
    elif metric_name == "walkin_done":
        rows = _fetch_events_breakup(parsed_ids, fd, td, mode="walkin_done")
    elif metric_name in CLICKABLE_METRICS:
        rows = _mock_breakup_rows(metric_name, parsed_ids, fd, td)
    else:
        rows = _mock_breakup_rows(metric_name, parsed_ids, fd, td)

    columns = _breakup_columns_for_rows(metric_name, rows)
    linkable = metric_name not in _BREAKUP_NO_LINK_METRICS
    return {
        "columns": columns,
        "rows": rows,
        "metric_name": metric_name,
        "linkable": linkable,
    }


def get_available_agents() -> list[dict]:
    """Agents available for the agent performance dashboard filter."""
    return _fetch_agents_meta_from_db()


def get_dashboard_data(
    *,
    granularity: str = "day_wise",
    from_date: str | None = None,
    to_date: str | None = None,
    agent_ids=None,
    city: str = "",
) -> dict:
    """Load pivot analytics from Agent Performance docs; filter by date range, agents, hub (city param = hubId)."""
    parsed_agent_ids = _parse_agent_ids(agent_ids)
    hub_id = (city or "").strip()

    docs = _fetch_performance_docs_from_db(
        from_date=from_date,
        to_date=to_date,
        agent_ids=parsed_agent_ids if parsed_agent_ids else None,
        hub_id=hub_id,
    )

    meta_list = _fetch_agents_meta_from_db()
    meta_by_id = {a["id"]: a for a in meta_list}
    cities = _fetch_distinct_hubs_from_db()
    default_range = _fetch_date_bounds_from_db()

    restrict = parsed_agent_ids if parsed_agent_ids else None
    agents_pivot = _agents_for_pivot(docs, restrict, meta_by_id)

    payload = build_analytics_payload(docs, agents_pivot, granularity)

    return {
        **payload,
        "agents": meta_list,
        "cities": cities,
        "default_date_range": default_range,
    }
