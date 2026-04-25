class EventCallbackStatus:
	SCHEDULED = "Scheduled"
	TRIGGERED = "Triggered"
	COMPLETED = "Completed"
	MISSED = "Missed"


class EventCallbackCategory:
	CALLBACK = "Callback"
	VISIT_DATE = "Visit Date"

class Roles:
	SYSTEM_USER = "System User"
	GUEST = "Guest"

class _EnumValues:
	EventCallbackStatus = EventCallbackStatus
	EventCallbackCategory = EventCallbackCategory
	Roles = Roles


EnumValues = _EnumValues()
