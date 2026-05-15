"""Agent Performance analytics dashboard (pivot data for CRM UI)."""

from __future__ import annotations

import hashlib
import json
import random
from calendar import month_name
from datetime import date, datetime, timedelta

import frappe
from frappe.utils import flt

MOCK_AGENTS = [
    {"id": "rahul@carrum.co.in", "name": "Rahul Sharma", "city": "Delhi"},
    {"id": "priya@carrum.co.in", "name": "Priya Singh", "city": "Mumbai"},
    {"id": "amit@carrum.co.in", "name": "Amit Kumar", "city": "Delhi"},
]

AGENT_PERFORMANCE_DOCTYPE = "Agent Performance"

_PERFORMANCE_FETCH_FIELDS = [
    "name",
    "date",
    "agent_id",
    "agent_name",
    "hubId",
    "hubName",
    "login_duration",
    "dialer_talktime_duration",
    "click2call_talktime_duration",
    "break_duration",
    "dispose_duration",
    "click2call_ring_duration",
    "total_dialer_connects",
    "total_manual_attempts",
    "total_manual_connects",
    "total_mannual_attempts",
    "total_mannual_connects",
    "psd_count",
    "fsd_count",
    "walkin_count",
]


def _agent_performance_table_ready() -> bool:
    return bool(frappe.db.exists("DocType", AGENT_PERFORMANCE_DOCTYPE))


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
    return {
        "date": _format_doc_date(row.get("date")),
        "agent_id": (row.get("agent_id") or "").strip(),
        "agent_name": (row.get("agent_name") or "").strip(),
        "hub_id": (row.get("hubId") or "").strip(),
        "hub_name": (row.get("hubName") or "").strip(),
        "city": (row.get("hubName") or "").strip(),
        "login_duration": _duration_to_seconds(row.get("login_duration")),
        "dialer_talktime_duration": _duration_to_seconds(row.get("dialer_talktime_duration")),
        "click2call_talktime_duration": _duration_to_seconds(row.get("click2call_talktime_duration")),
        "break_duration": _duration_to_seconds(row.get("break_duration")),
        "dispose_duration": _duration_to_seconds(row.get("dispose_duration")),
        "click2call_ring_duration": _duration_to_seconds(row.get("click2call_ring_duration")),
        "total_dialer_connects": _int_field(row, "total_dialer_connects"),
        "total_manual_attempts": _int_field(
            row,
            "total_manual_attempts",
            "total_mannual_attempts",
        ),
        "total_manual_connects": _int_field(
            row,
            "total_manual_connects",
            "total_mannual_connects",
        ),
        "walkin_count": _int_field(row, "walkin_count"),
        "psd_count": _int_field(row, "psd_count"),
        "fsd_count": _int_field(row, "fsd_count"),
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

    try:
        rows = frappe.get_all(
            AGENT_PERFORMANCE_DOCTYPE,
            filters=filters or None,
            fields=_PERFORMANCE_FETCH_FIELDS,
            limit_page_length=0,
            order_by="date asc, agent_id asc",
        )
    except Exception:
        # Field renames / optional columns in older sites
        fields = [f for f in _PERFORMANCE_FETCH_FIELDS if f not in ("total_mannual_attempts", "total_mannual_connects")]
        rows = frappe.get_all(
            AGENT_PERFORMANCE_DOCTYPE,
            filters=filters or None,
            fields=fields,
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
        MOCK_AGENT_PERFORMANCE_DOCS.append(
            {
                **base,
                "agent_id": agent["id"],
                "agent_name": agent["name"],
                "city": agent["city"],
                "login_duration": round(base["login_duration"] * factor),
                "dialer_talktime_duration": round(base["dialer_talktime_duration"] * factor),
                "break_duration": round(base["break_duration"] * factor),
                "dispose_duration": round(base["dispose_duration"] * factor),
                "click2call_ring_duration": round(base["click2call_ring_duration"] * factor),
                "total_dialer_connects": max(1, round(base["total_dialer_connects"] * factor)),
                "total_manual_attempts": max(0, round(base["total_manual_attempts"] * factor)),
                "total_manual_connects": max(0, round(base["total_manual_connects"] * factor)),
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


def _format_cell_value(value, fmt: str) -> str:
    if value is None or value == "":
        return "—"
    if fmt == "duration":
        return _format_duration(value)
    if fmt == "percent":
        n = float(value)
        rounded = round(n * 10) / 10
        text = f"{int(rounded)}" if rounded % 1 == 0 else f"{rounded:.1f}"
        return f"{text}%"
    return str(value)


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


def _merge_docs(docs: list[dict]) -> dict:
    if not docs:
        return {}
    if len(docs) == 1:
        return dict(docs[0])

    merged = dict(docs[0])
    count = len(docs)
    for doc in docs[1:]:
        merged["login_duration"] = merged.get("login_duration", 0) + doc.get("login_duration", 0)
        merged["dialer_talktime_duration"] = merged.get("dialer_talktime_duration", 0) + doc.get(
            "dialer_talktime_duration", 0
        )
        merged["click2call_talktime_duration"] = merged.get("click2call_talktime_duration", 0) + doc.get(
            "click2call_talktime_duration", 0
        )
        merged["break_duration"] = merged.get("break_duration", 0) + doc.get("break_duration", 0)
        merged["dispose_duration"] = merged.get("dispose_duration", 0) + doc.get("dispose_duration", 0)
        merged["click2call_ring_duration"] = merged.get("click2call_ring_duration", 0) + doc.get(
            "click2call_ring_duration", 0
        )
        merged["total_dialer_connects"] = merged.get("total_dialer_connects", 0) + doc.get(
            "total_dialer_connects", 0
        )
        merged["total_manual_attempts"] = merged.get("total_manual_attempts", 0) + doc.get(
            "total_manual_attempts", 0
        )
        merged["total_manual_connects"] = merged.get("total_manual_connects", 0) + doc.get(
            "total_manual_connects", 0
        )
        merged["walkin_count"] = merged.get("walkin_count", 0) + doc.get("walkin_count", 0)
        merged["psd_count"] = merged.get("psd_count", 0) + doc.get("psd_count", 0)
        merged["fsd_count"] = merged.get("fsd_count", 0) + doc.get("fsd_count", 0)

    merged["login_duration"] = round(merged["login_duration"] / count)
    merged["dialer_talktime_duration"] = round(merged["dialer_talktime_duration"] / count)
    merged["click2call_talktime_duration"] = round(merged["click2call_talktime_duration"] / count)
    merged["break_duration"] = round(merged["break_duration"] / count)
    merged["dispose_duration"] = round(merged["dispose_duration"] / count)
    merged["click2call_ring_duration"] = round(merged["click2call_ring_duration"] / count)
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


def _metric_definitions():
    return [
        {
            "metric_name": "login_duration",
            "label": "Avg daily login",
            "group": "time_metrics",
            "format": "duration",
            "section_end": False,
            "get_value": lambda d: d.get("login_duration"),
        },
        {
            "metric_name": "dialer_talktime_duration",
            "label": "Avg daily talktime",
            "group": "time_metrics",
            "format": "duration",
            "get_value": lambda d: (d.get("dialer_talktime_duration") or 0)
            + (d.get("click2call_talktime_duration") or 0),
        },
        {
            "metric_name": "break_duration",
            "label": "Avg daily pause",
            "group": "time_metrics",
            "format": "duration",
            "get_value": lambda d: d.get("break_duration"),
        },
        {
            "metric_name": "click2call_ring_duration",
            "label": "Avg daily ring",
            "group": "time_metrics",
            "format": "duration",
            "get_value": lambda d: d.get("click2call_ring_duration"),
        },
        {
            "metric_name": "dispose_duration",
            "label": "Avg daily dispo",
            "group": "time_metrics",
            "format": "duration",
            "get_value": lambda d: d.get("dispose_duration"),
        },
        {
            "metric_name": "aht",
            "label": "Avg AHT",
            "group": "time_metrics",
            "format": "duration",
            "section_end": True,
            "get_value": lambda d: (
                round(
                    (
                        (d.get("dialer_talktime_duration") or 0)
                        + (d.get("click2call_talktime_duration") or 0)
                    )
                    / (
                        (d.get("total_dialer_connects") or 0)
                        + (d.get("total_manual_connects") or 0)
                    )
                )
                if (d.get("total_dialer_connects") or 0) + (d.get("total_manual_connects") or 0)
                else 0
            ),
        },
        {
            "metric_name": "total_attempts",
            "label": "Total attempts",
            "group": "attempt_metrics",
            "format": "number",
            "get_value": lambda d: (d.get("total_dialer_connects") or 0)
            + (d.get("total_manual_attempts") or 0),
        },
        {
            "metric_name": "unique_attempts",
            "label": "Unique attempts",
            "group": "attempt_metrics",
            "format": "number",
            "get_value": lambda d: round(
                ((d.get("total_dialer_connects") or 0) + (d.get("total_manual_attempts") or 0)) * 0.92
            ),
        },
        {
            "metric_name": "total_connects",
            "label": "Total connects",
            "group": "attempt_metrics",
            "format": "number",
            "get_value": lambda d: (d.get("total_dialer_connects") or 0)
            + (d.get("total_manual_connects") or 0),
        },
        {
            "metric_name": "unique_connects",
            "label": "Unique connects",
            "group": "attempt_metrics",
            "format": "number",
            "get_value": lambda d: round(
                ((d.get("total_dialer_connects") or 0) + (d.get("total_manual_connects") or 0)) * 0.94
            ),
        },
        {
            "metric_name": "unique_interests",
            "label": "Unique interests",
            "group": "conversion_metrics",
            "format": "number",
            "get_value": lambda d: max(
                0,
                round(
                    ((d.get("total_dialer_connects") or 0) + (d.get("total_manual_connects") or 0)) * 0.12
                ),
            ),
        },
        {
            "metric_name": "interest_pct",
            "label": "Interest %",
            "group": "conversion_metrics",
            "format": "percent",
            "get_value": lambda d: (
                (
                    max(
                        0,
                        round(
                            (
                                (d.get("total_dialer_connects") or 0)
                                + (d.get("total_manual_connects") or 0)
                            )
                            * 0.12
                        ),
                    )
                    / (
                        (d.get("total_dialer_connects") or 0)
                        + (d.get("total_manual_connects") or 0)
                    )
                    * 100
                )
                if (d.get("total_dialer_connects") or 0) + (d.get("total_manual_connects") or 0)
                else 0
            ),
        },
        {
            "metric_name": "unique_date_confirm",
            "label": "Unique date confirm",
            "group": "conversion_metrics",
            "format": "number",
            "get_value": lambda d: max(
                0,
                round(
                    ((d.get("total_dialer_connects") or 0) + (d.get("total_manual_connects") or 0)) * 0.05
                ),
            ),
        },
        {
            "metric_name": "date_confirm_pct",
            "label": "Date confirm %",
            "group": "conversion_metrics",
            "format": "percent",
            "section_end": True,
            "get_value": lambda d: (
                (
                    max(
                        0,
                        round(
                            (
                                (d.get("total_dialer_connects") or 0)
                                + (d.get("total_manual_connects") or 0)
                            )
                            * 0.05
                        ),
                    )
                    / (
                        (d.get("total_dialer_connects") or 0)
                        + (d.get("total_manual_connects") or 0)
                    )
                    * 100
                )
                if (d.get("total_dialer_connects") or 0) + (d.get("total_manual_connects") or 0)
                else 0
            ),
        },
        {
            "metric_name": "walkin_count",
            "label": "Walk-in done",
            "group": "walkin_metrics",
            "format": "number",
            "get_value": lambda d: d.get("walkin_count") or 0,
        },
        {
            "metric_name": "psd_count",
            "label": "PSD count",
            "group": "psd_metrics",
            "format": "number",
            "get_value": lambda d: d.get("psd_count") or 0,
        },
        {
            "metric_name": "fsd_count",
            "label": "FSD count",
            "group": "psd_metrics",
            "format": "number",
            "get_value": lambda d: d.get("fsd_count") or 0,
        },
        {
            "metric_name": "interest_to_psd_pct",
            "label": "Interest to PSD %",
            "group": "conversion_metrics",
            "format": "percent",
            "get_value": lambda d: (
                ((d.get("psd_count") or 0) / interests * 100)
                if (
                    interests := max(
                        0,
                        round(
                            (
                                (d.get("total_dialer_connects") or 0)
                                + (d.get("total_manual_connects") or 0)
                            )
                            * 0.12
                        ),
                    )
                )
                else 0
            ),
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
    for definition in _metric_definitions():
        rows.append(
            {
                "metric_name": definition["metric_name"],
                "label": definition["label"],
                "group": definition["group"],
                "format": definition["format"],
                "section_end": bool(definition.get("section_end")),
                "values": [
                    _format_cell_value(definition["get_value"](doc), definition["format"])
                    for doc in column_docs
                ],
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


def _pause_log_day_span(period_key: str, granularity: str) -> tuple[datetime.date, datetime.date]:
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


def get_agent_pause_break_logs(
    agent_id: str,
    period_key: str,
    granularity: str = "day_wise",
) -> list[dict]:
    """
    Return pause/break intervals for the drawer when drilling into Avg daily pause.
    Mock rows until this is wired to User dialer session break logs (or live SQL).
    Each item: start_time, end_time, user, user_dialer_session_log.
    """
    agent_id = (agent_id or "").strip()
    period_key = (period_key or "").strip()
    if not agent_id or not period_key:
        return []

    granularity = _normalize_granularity(granularity)
    try:
        span_start, span_end = _pause_log_day_span(period_key, granularity)
    except ValueError:
        return []

    seed = int(hashlib.md5(f"{agent_id}:{period_key}:{granularity}".encode()).hexdigest()[:12], 16)
    rnd = random.Random(seed)
    n_breaks = rnd.randint(2, 5)
    total_days = (span_end - span_start).days + 1

    rows: list[dict] = []
    alias = (agent_id.split("@")[0] or "AGT")[:6].upper()

    for i in range(n_breaks):
        day_off = rnd.randint(0, max(0, total_days - 1))
        day = span_start + timedelta(days=day_off)
        hour = rnd.randint(9, 17)
        minute = rnd.choice([0, 5, 10, 15, 20, 30, 40, 45])
        second = rnd.choice([0, 15, 30])
        start_dt = datetime.combine(day, datetime.min.time()).replace(
            hour=hour,
            minute=minute,
            second=second,
        )
        duration_mins = rnd.randint(3, 28)
        end_dt = start_dt + timedelta(minutes=duration_mins)

        sess = f"DSL-{alias}-{seed % 9000 + 1000}-{i}"

        rows.append(
            {
                "name": f"BREAK-{alias}-{seed % 10000}-{i}",
                "start_time": start_dt.strftime("%Y-%m-%d %H:%M:%S"),
                "end_time": end_dt.strftime("%Y-%m-%d %H:%M:%S"),
                "user": agent_id,
                "user_dialer_session_log": sess,
            }
        )

    rows.sort(key=lambda r: r["start_time"])
    return rows


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
