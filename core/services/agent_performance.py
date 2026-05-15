from datetime import timedelta
import frappe
from frappe.utils import flt, get_datetime, now_datetime

from core.constants.enums import EnumValues
import redis

# Max seconds credited per heartbeat (tab backgrounded / clock skew).
_HEARTBEAT_MAX_DELTA_SEC = 120


def _duration_field_to_seconds(val) -> int:
    """Frappe Duration fields are stored / exposed as total seconds (int/float)."""
    if val is None:
        return 0
    if isinstance(val, int):
        return max(0, val)
    if isinstance(val, float):
        return max(0, int(val))
    return max(0, int(flt(val) or 0))


def _as_datetime(val):
    if val is None:
        return None
    if hasattr(val, "date") and hasattr(val, "hour"):
        return val
    if isinstance(val, str) and val.strip():
        try:
            return get_datetime(val)
        except Exception:
            return None
    return None


class AgentPerformanceService:
    def __init__(self):
        pass

    def _get_today_agent_performance_name(self, user_id: str) -> str | None:
        user_id = (user_id or "").strip()
        if not user_id:
            return None
        return frappe.db.get_value(
            EnumValues.ReferenceDocType.AGENT_PERFORMANCE,
            {"agent_id": user_id, "date": frappe.utils.today()},
            "name",
        )

    def handle_update_agent_performance_on_heartbeat(self, agent_performance_doc):
        now = now_datetime()
        last = _as_datetime(agent_performance_doc.get("last_heartbeat_time"))

        if last:
            delta = (now - last).total_seconds()
        else:
            delta = 0.0

        delta = max(0.0, min(delta, float(_HEARTBEAT_MAX_DELTA_SEC)))

        base = _duration_field_to_seconds(agent_performance_doc.get("login_duration"))
        agent_performance_doc.login_duration = base + int(delta)
        agent_performance_doc.last_heartbeat_time = now
        agent_performance_doc.save(ignore_permissions=True)

    def create_agent_performance_doc(self, user_id: str):
        user_id = (user_id or "").strip()
        if not user_id or not frappe.db.exists("User", user_id):
            return None

        agent_name = (
            frappe.db.get_value("User", user_id, "full_name") or user_id
        ).strip()

        doc = frappe.new_doc(EnumValues.ReferenceDocType.AGENT_PERFORMANCE)
        doc.agent_id = user_id
        doc.agent_name = agent_name
        doc.date = frappe.utils.today()
        doc.insert(ignore_permissions=True)
        return doc

    def _ensure_today_telecaller_agents_performance(self) -> None:
        user_ids = frappe.get_all(
            "Has Role",
            filters={
                "parenttype": "User",
                "role": EnumValues.Roles.TELECALLER,
            },
            pluck="parent",
            distinct=True,
        )
        today_d = frappe.utils.today()
        for uid in user_ids or []:
            if not uid or uid in ("Guest", "Administrator"):
                continue
            exists = frappe.db.exists(
                EnumValues.ReferenceDocType.AGENT_PERFORMANCE,
                {"agent_id": uid, "date": today_d},
            )
            if not exists:
                self.create_agent_performance_doc(uid)

        return user_ids


    def cron_task_update_today_telecaller_agents_performance_5_minute(self) -> None:
        """Every 5 minutes cron: update today's Agent Performance data for all telecallers."""
        user_ids = self._ensure_today_telecaller_agents_performance()
        for user_id in user_ids or []:
            self.update_today_agent_performance_data_for_telecaller(user_id)


    def update_today_agent_performance_data_for_telecaller(self, user_id: str) -> None:
        agent_performance_name = self._get_today_agent_performance_name(user_id)
        if not agent_performance_name:
            return
        agent_performance_doc = frappe.get_doc(
            EnumValues.ReferenceDocType.AGENT_PERFORMANCE, agent_performance_name
        )
        day_start = frappe.utils.get_datetime(frappe.utils.today())
        day_end = day_start + timedelta(days=1)
        call_sessions = frappe.get_all(
            EnumValues.ReferenceDocType.CALL_SESSION,
            filters={
                "agent": user_id,
                "agent_answered_at": ("between", [day_start, day_end]),
            },
            fields=["*"],
        )

        dialer_talktime_duration = 0
        total_dialer_connects = 0
        total_click2call_attempts = 0
        total_click2call_connects = 0
        total_unique_attempt_phones = set()
        total_unique_connect_phones = set()
        click2call_talktime_duration = 0
        click2call_ring_duration = 0
        for call_session in call_sessions:
            total_unique_attempt_phones.add(call_session.phone_number)

            if call_session.connected_at is not None:
                total_unique_connect_phones.add(call_session.phone_number)

            if call_session.calling_method == "Dialer":
                total_dialer_connects += 1
                dialer_talktime_duration += _duration_field_to_seconds(
                    call_session.duration
                )

            else:
                total_click2call_attempts += 1
                if call_session.connected_at is not None:
                    total_click2call_connects += 1

                click2call_talktime_duration += _duration_field_to_seconds(
                    call_session.duration
                )
                click2call_ring_duration += _duration_field_to_seconds(
                    call_session.ring_duration
                )

        session_duration,dialer_session_count = self._calculate_dialer_session_duration_count(user_id)
        break_duration, break_count = self._calculate_break_duration_count(user_id)
        
        today_schedules_followup = self._calculate_today_schedules_followup_count(user_id)
        today_scheduled_followup = self._calculate_today_scheduled_followup_count(user_id)
        today_completed_scheduled_followup = self._calculate_today_completed_scheduled_followup_count(user_id)

        agent_performance_doc.dialer_talktime_duration = dialer_talktime_duration
        agent_performance_doc.click2call_talktime_duration = click2call_talktime_duration
        agent_performance_doc.click2call_ring_duration = click2call_ring_duration

        agent_performance_doc.total_dialer_connects = total_dialer_connects
        agent_performance_doc.total_click2call_attempts = total_click2call_attempts
        agent_performance_doc.total_click2call_connects = total_click2call_connects
        agent_performance_doc.total_unique_attempts = len(total_unique_attempt_phones)
        agent_performance_doc.total_unique_connects = len(total_unique_connect_phones)

        agent_performance_doc.schedules_followup = today_schedules_followup
        agent_performance_doc.scheduled_followup = today_scheduled_followup
        agent_performance_doc.completed_scheduled_followup = today_completed_scheduled_followup

        agent_performance_doc.dialer_session_duration = session_duration
        agent_performance_doc.dialer_session_count = dialer_session_count
        agent_performance_doc.break_duration = break_duration
        agent_performance_doc.break_count = break_count

        agent_performance_doc.save(ignore_permissions=True)

    def _calculate_today_schedules_followup_count(self, user_id: str) -> int:
        today = frappe.utils.today()
        today_midnight = frappe.utils.get_datetime(today)
        today_end = today_midnight + timedelta(days=1)
        return frappe.db.count(
            "Event",
            filters={
                "owner": user_id,
                "event_category": EnumValues.EventCallbackCategory.CALLBACK,
                "creation": ("between", [today_midnight, today_end]),
            }
        )

    def _calculate_today_scheduled_followup_count(self, user_id: str) -> int:
        today = frappe.utils.today()
        today_midnight = frappe.utils.get_datetime(today)
        today_end = today_midnight + timedelta(days=1)
        return frappe.db.count(
            "Event",
            filters={
                "owner": user_id,
                "event_category": EnumValues.EventCallbackCategory.CALLBACK,
                "call_at": ("between", [today_midnight, today_end]),
                "callback_status": EnumValues.EventCallbackStatus.SCHEDULED
            }
        )

    def _calculate_today_completed_scheduled_followup_count(self, user_id: str) -> int:
        today = frappe.utils.today()
        today_midnight = frappe.utils.get_datetime(today)
        today_end = today_midnight + timedelta(days=1)
        return frappe.db.count(
            "Event",
            filters={
                "owner": user_id,
                "event_category": EnumValues.EventCallbackCategory.CALLBACK,
                "call_at": ("between", [today_midnight, today_end]),
                "callback_status": EnumValues.EventCallbackStatus.COMPLETED
            }
        )

    def _calculate_dialer_session_duration_count(self, user_id: str) -> tuple[int, int]:
        session_duration = 0
        session_count = 0
        today = frappe.utils.today()
        now = frappe.utils.now_datetime()
        today_midnight = frappe.utils.get_datetime(today)

        common_fields = ["name", "user", "campaign_id", "active_at", "inactive_at", "status", "inactive_reason"]

        # Query 1: Sessions that started today
        sessions_started_today = frappe.db.get_all(
            "User dialer session logs",
            filters={
                "active_at": ["between", [today, today + " 23:59:59.999999"]],
                "user": user_id
            },
            fields=common_fields
        )

        # Query 2: Sessions that started before today but still active (bleeding into today)
        sessions_still_active = frappe.db.get_all(
            "User dialer session logs",
            filters={
                "active_at": ["<", today],
                "inactive_at": ["is", "not set"],
                "user": user_id
            },
            fields=common_fields
        )

        # Query 3: Sessions that started before today but ended today
        sessions_ended_today = frappe.db.get_all(
            "User dialer session logs",
            filters={
                "active_at": ["<", today],
                "inactive_at": ["between", [today, today + " 23:59:59.999999"]],
                "user": user_id
            },
            fields=common_fields
        )

        # Merge all, deduplicate by name (if you include 'name' in fields)
        all_logs = { log.name: log for log in (sessions_started_today + sessions_still_active + sessions_ended_today) }.values()
        # OR if not using 'name', just concat (no duplicates possible across these 3 queries)
        all_logs = sessions_started_today + sessions_still_active + sessions_ended_today

        for log in all_logs:
            if not log.active_at:
                continue

            end_time = log.inactive_at if log.inactive_at else now

            # Clamp start to today midnight for sessions that bled in from yesterday
            start_time = max(log.active_at, today_midnight)

            if end_time > today_midnight:
                duration_seconds = (end_time - start_time).total_seconds()
                session_duration += max(0, duration_seconds)

        session_count = len(all_logs)
        return session_duration, session_count

    def _calculate_break_duration_count(self, user_id: str) -> tuple[int, int]:
        break_duration = 0
        break_count = 0
        today = frappe.utils.today()
        now = frappe.utils.now_datetime()
        today_midnight = frappe.utils.get_datetime(today)

        common_fields = ["name", "user", "start_time", "end_time"]

        # Query 1: Breaks that started today
        sessions_started_today = frappe.db.get_all(
            "User dialer session break logs",
            filters={
                "start_time": ["between", [today, today + " 23:59:59.999999"]],
                "user": user_id,
            },
            fields=common_fields,
        )

        # Query 2: Breaks that started before today but still open (bleed into today)
        sessions_still_active = frappe.db.get_all(
            "User dialer session break logs",
            filters={
                "start_time": ["<", today],
                "end_time": ["is", "not set"],
                "user": user_id,
            },
            fields=common_fields,
        )

        # Query 3: Breaks that started before today but ended today
        sessions_ended_today = frappe.db.get_all(
            "User dialer session break logs",
            filters={
                "start_time": ["<", today],
                "end_time": ["between", [today, today + " 23:59:59.999999"]],
                "user": user_id,
            },
            fields=common_fields,
        )

        all_logs = (
            sessions_started_today + sessions_still_active + sessions_ended_today
        )

        for log in all_logs:
            if not log.start_time:
                continue

            end_time = log.end_time if log.end_time else now
            start_time = max(log.start_time, today_midnight)

            if end_time > today_midnight:
                duration_seconds = (end_time - start_time).total_seconds()
                break_duration += max(0, duration_seconds)

        return break_duration, break_count

    def cron_task_update_today_agent_performance_data(self) -> None:
        """Every 5 minutes: ensure today's row exists (idempotent)."""
        self._ensure_today_telecaller_agents_performance()

    def login_heartbeat(self, user: str):
        user = (user or "").strip()
        if not user or user == "Guest":
            return
        if EnumValues.Roles.TELECALLER not in frappe.get_roles(user):
            return

        with frappe.cache().lock(f"agent_performance_heartbeat_lock_{user}", timeout=10, blocking=True, blocking_timeout=10):
            name = self._get_today_agent_performance_name(user)
            if name:
                doc = frappe.get_doc(EnumValues.ReferenceDocType.AGENT_PERFORMANCE, name)
            else:
                doc = self.create_agent_performance_doc(user)

            if not doc:
                return

            self.handle_update_agent_performance_on_heartbeat(doc)

agent_performance_service = AgentPerformanceService()
