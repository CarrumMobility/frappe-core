from datetime import timedelta
import logging

from core.constants.app_constant import AppConstants
import frappe
from frappe.utils import flt, get_datetime, getdate, now_datetime, today

from core.constants.enums import EnumValues
import redis

log = frappe.logger("agent_performance")
log.setLevel(logging.INFO)
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


def _event_followup_visit_date_sql_expr() -> str:
    """Calendar day of scheduled callback / visit (Event ``call_at`` or ``starts_on``)."""
    cols = frappe.db.get_table_columns("Event") or []
    if "call_at" in cols:
        return "DATE(COALESCE(`call_at`, `starts_on`))"
    return "DATE(`starts_on`)"


def _call_session_connected_field() -> str:
    doctype = EnumValues.ReferenceDocType.CALL_SESSION
    if frappe.db.has_column(doctype, "connected_at"):
        return "connected_at"
    return "lead_answered_at"


def _call_session_disconnect_field() -> str:
    doctype = EnumValues.ReferenceDocType.CALL_SESSION
    if frappe.db.has_column(doctype, "disconnect_at"):
        return "disconnect_at"
    return "hangup_at"


def _dispose_seconds_for_call_session(call_session: dict) -> int:
    """Seconds from disconnect to dispose, capped at MAX_TIME_TO_DISPOSE_SEC."""
    max_sec = AppConstants.MAX_TIME_TO_DISPOSE_SEC
    disconnect_at = _as_datetime(
        call_session.get(_call_session_disconnect_field())
    )
    if not disconnect_at:
        return 0

    disposed_at = _as_datetime(call_session.get("disposed_at"))
    now = now_datetime()

    if not disposed_at:
        if disconnect_at + timedelta(seconds=max_sec) < now:
            return max_sec
        return 0

    delta_sec = int((disposed_at - disconnect_at).total_seconds())
    if delta_sec <= 0:
        return 0
    return min(delta_sec, max_sec)


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
        log.info("CRON RUNNING: update today's Agent Performance data for all telecallers")

        user_ids = self._ensure_today_telecaller_agents_performance()
        for user_id in user_ids or []:
            if not user_id or user_id in ("Guest", "Administrator"):
                continue
            self.update_today_agent_performance_data_for_telecaller(user_id)
        log.info("CRON COMPLETED: update today's Agent Performance data for all telecallers")
        frappe.db.commit()

    def _fetch_today_call_sessions(self, user_id: str) -> list[dict]:
        """Today's call sessions for an agent (date = Coalesce(connected_at, creation))."""
        from frappe.query_builder import DocType
        from frappe.query_builder.functions import Coalesce

        doctype = EnumValues.ReferenceDocType.CALL_SESSION
        if not frappe.db.exists("DocType", doctype):
            return []

        connected_field = _call_session_connected_field()
        CS = DocType(doctype)
        connected_col = getattr(CS, connected_field, None)
        if connected_col is None:
            return []

        day_start = frappe.utils.get_datetime(frappe.utils.today())
        day_end = day_start + timedelta(days=1)
        date_expr = Coalesce(connected_col, CS.creation)

        disconnect_field = _call_session_disconnect_field()
        disconnect_col = getattr(CS, disconnect_field, None)

        select_cols = [
            CS.name,
            CS.calling_method,
            CS.lead_phone,
            CS.duration,
            CS.status,
            connected_col.as_("connected_at"),
        ]
        if disconnect_col is not None:
            select_cols.append(disconnect_col.as_(disconnect_field))
        if frappe.db.has_column(doctype, "disposed_at"):
            select_cols.append(CS.disposed_at)
        if frappe.db.has_column(doctype, "disposition_status"):
            select_cols.append(CS.disposition_status)
        if frappe.db.has_column(doctype, "ring_duration"):
            select_cols.append(CS.ring_duration)
        if frappe.db.has_column(doctype, "lead_callback_datetime"):
            select_cols.append(CS.lead_callback_datetime)

        return (
            frappe.qb.from_(CS)
            .select(*select_cols)
            .where(CS.agent == user_id)
            .where(date_expr >= day_start)
            .where(date_expr < day_end)
            .run(as_dict=True)
        )

    def update_today_agent_performance_data_for_telecaller(self, user_id: str) -> None:
        log.info(f"STARTING: UPDATING AGENT PERFORMANCE DATA FOR TELECALLER: {user_id}")
        agent_performance_name = self._get_today_agent_performance_name(user_id)
        if not agent_performance_name:
            log.info(f"NOT FOUND: AGENT PERFORMANCE DOCUMENT FOR TELECALLER: {user_id} - NO AGENT PERFORMANCE DOCUMENT FOUND")
            return
        
        agent_performance_doc = frappe.get_doc(
            EnumValues.ReferenceDocType.AGENT_PERFORMANCE, agent_performance_name
        )
        call_sessions = self._fetch_today_call_sessions(user_id)

        dialer_talktime_duration = 0
        total_dialer_connects = 0
        total_click2call_attempts = 0
        total_click2call_connects = 0
        total_unique_attempt_phones = set()
        total_unique_connect_phones = set()
        click2call_talktime_duration = 0
        click2call_ring_duration = 0
        unique_interest_phones = set()
        total_dispose_duration = 0
        
        for call_session in call_sessions:
            phone = (call_session.get("lead_phone") or "").strip()
            is_connected = bool(call_session.get("connected_at"))
            calling_method = call_session.get("calling_method") or ""
            disposition = (call_session.get("disposition_status") or "").strip()
            if call_session.get("status") not in (
                EnumValues.CallSessionStatus.DISPOSED,
                EnumValues.CallSessionStatus.DISCONNECTED,
            ):
                continue

            total_dispose_duration += _dispose_seconds_for_call_session(call_session)

            if disposition == EnumValues.LeadStatus.INTERESTED and phone:
                unique_interest_phones.add(phone)

            if calling_method == EnumValues.CallingMethod.Dialer:
                if not is_connected:
                    continue
                total_dialer_connects += 1
                if phone:
                    total_unique_attempt_phones.add(phone)
                    total_unique_connect_phones.add(phone)
                dialer_talktime_duration += _duration_field_to_seconds(call_session.get("duration"))
                continue

            if calling_method == EnumValues.CallingMethod.Click2Call:
                total_click2call_attempts += 1
                if phone:
                    total_unique_attempt_phones.add(phone)
                if is_connected:
                    total_click2call_connects += 1
                    if phone:
                        total_unique_connect_phones.add(phone)
                click2call_talktime_duration += _duration_field_to_seconds(
                    call_session.get("duration")
                )
                click2call_ring_duration += _duration_field_to_seconds(
                    call_session.get("ring_duration")
                )

        session_duration,dialer_session_count = self._calculate_dialer_session_duration_count(user_id)
        break_duration, break_count = self._calculate_break_duration_count(user_id)
        
        today_schedules_followup = self._calculate_today_schedules_followup_count(user_id)
        today_scheduled_followup = self._calculate_today_scheduled_followup_count(user_id)
        today_completed_scheduled_followup = (
            self._calculate_today_completed_scheduled_followup_count(user_id)
        )
        unique_schedules_walkin = self._calculate_unique_schedules_walkin_count(user_id)

        agent_performance_doc.dialer_talktime_duration = dialer_talktime_duration
        agent_performance_doc.click2call_talktime_duration = click2call_talktime_duration
        agent_performance_doc.dispose_duration = total_dispose_duration

        if hasattr(agent_performance_doc, "click2call_ring_time"):
            agent_performance_doc.click2call_ring_time = click2call_ring_duration
        else:
            agent_performance_doc.click2call_ring_duration = click2call_ring_duration

        agent_performance_doc.total_dialer_connects = total_dialer_connects
        agent_performance_doc.total_click2call_attempts = total_click2call_attempts
        agent_performance_doc.total_click2call_connects = total_click2call_connects
        agent_performance_doc.total_unique_attempts = len(total_unique_attempt_phones)
        agent_performance_doc.total_unique_connects = len(total_unique_connect_phones)
        agent_performance_doc.total_unique_interests = len(unique_interest_phones)
        
        agent_performance_doc.schedules_followup = today_schedules_followup
        agent_performance_doc.scheduled_followup = today_scheduled_followup
        agent_performance_doc.completed_scheduled_followup = today_completed_scheduled_followup
        if hasattr(agent_performance_doc, "unique_schedules_walkin"):
            agent_performance_doc.unique_schedules_walkin = unique_schedules_walkin
        elif hasattr(agent_performance_doc, "unique_date_confirmed"):
            agent_performance_doc.unique_date_confirmed = unique_schedules_walkin

        agent_performance_doc.dialer_session_duration = session_duration
        agent_performance_doc.dialer_session_count = dialer_session_count
        agent_performance_doc.break_duration = break_duration
        agent_performance_doc.break_count = break_count

        log.info(f"SAVING: UPDATING AGENT PERFORMANCE DATA FOR TELECALLER: {user_id}")
        agent_performance_doc.save(ignore_permissions=True)
        log.info(f"SAVED , END: UPDATING AGENT PERFORMANCE DATA FOR TELECALLER: {user_id}")

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
        """Callback follow-ups scheduled for today (visit/call date = today)."""
        return self._count_callback_events_by_visit_date(user_id)

    def _calculate_today_completed_scheduled_followup_count(self, user_id: str) -> int:
        """Callback follow-ups scheduled for today with status Missed."""
        return self._count_callback_events_by_visit_date(
            user_id,
            callback_status=EnumValues.EventCallbackStatus.MISSED,
        )

    def _count_callback_events_by_visit_date(
        self, user_id: str, *, callback_status: str | None = None
    ) -> int:
        user_id = (user_id or "").strip()
        if not user_id:
            return 0

        date_x = _event_followup_visit_date_sql_expr()
        conditions = [
            "`owner` = %(owner)s",
            "`event_category` = %(cat)s",
            f"{date_x} = %(today)s",
        ]
        params: dict = {
            "owner": user_id,
            "cat": EnumValues.EventCallbackCategory.CALLBACK,
            "today": getdate(today()),
        }
        if callback_status:
            conditions.append("`callback_status` = %(status)s")
            params["status"] = callback_status

        return int(
            frappe.db.sql(
                f"""
                SELECT COUNT(*) FROM `tabEvent`
                WHERE {" AND ".join(conditions)}
                """,
                params,
            )[0][0]
            or 0
        )

    def _calculate_unique_schedules_walkin_count(self, user_id: str) -> int:
        """Distinct CRM leads with a Visit Date event created today."""
        user_id = (user_id or "").strip()
        if not user_id:
            return 0

        today_s = today()
        today_midnight = get_datetime(today_s)
        today_end = today_midnight + timedelta(days=1)
        rows = frappe.db.sql(
            """
            SELECT DISTINCT `reference_docname`
            FROM `tabEvent`
            WHERE `owner` = %(owner)s
              AND `event_category` = %(cat)s
              AND `reference_doctype` = %(ref_dt)s
              AND IFNULL(`reference_docname`, '') != ''
              AND `creation` >= %(start)s
              AND `creation` < %(end)s
            """,
            {
                "owner": user_id,
                "cat": EnumValues.EventCallbackCategory.VISIT_DATE,
                "ref_dt": EnumValues.ReferenceDocType.CRM_LEAD,
                "start": today_midnight,
                "end": today_end,
            },
        )
        return len(rows or [])

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

        all_logs = {
            log.name: log
            for log in (
                sessions_started_today + sessions_still_active + sessions_ended_today
            )
        }.values()

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

        all_logs = {
            log.name: log
            for log in (
                sessions_started_today + sessions_still_active + sessions_ended_today
            )
        }.values()

        for log in all_logs:
            if not log.start_time:
                continue

            end_time = log.end_time if log.end_time else now
            start_time = max(log.start_time, today_midnight)

            if end_time > today_midnight:
                duration_seconds = (end_time - start_time).total_seconds()
                break_duration += max(0, duration_seconds)

        break_count = len(all_logs)
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

def cron_task_update_today_telecaller_agents_performance_5_minute():
    agent_performance_service.cron_task_update_today_telecaller_agents_performance_5_minute()