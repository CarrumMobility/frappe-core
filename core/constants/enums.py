class EventCallbackStatus:
	SCHEDULED = "Scheduled"
	TRIGGERED = "Triggered"
	COMPLETED = "Completed"
	MISSED = "Missed"


class EventCallbackCategory:
	CALLBACK = "Callback"
	VISIT_DATE = "Visit Date"


class _EnumValues:
	EventCallbackStatus = EventCallbackStatus
	EventCallbackCategory = EventCallbackCategory


EnumValues = _EnumValues()
