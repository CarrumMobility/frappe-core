class EventCallbackStatus:
	SCHEDULED = "Scheduled"
	TRIGGERED = "Triggered"
	COMPLETED = "Completed"
	MISSED = "Missed"
	OVERRIDE = "Override"


class EventCallbackCategory:
	CALLBACK = "Callback"
	VISIT_DATE = "Visit Date"

class Roles:
	SYSTEM_USER = "System User"
	GUEST = "Guest"

class LeadType:
	LEAD = "LEAD"
	DRIVER = "DRIVER"

class CallDirection:
	INBOUND = "INBOUND"
	OUTBOUND = "OUTBOUND"

class CallingMethod:
	Dialer = "Dialer"
	Click2Call = "Click2Call"

class CallSessionStatus:
	INITIATED = "INITIATED"
	FAILED = "FAILED"
	AGENT_CONNECTED = "AGENT_CONNECTED"
	CUSTOMER_CONNECTED = "CUSTOMER_CONNECTED"
	NOT_CONNECTED = "NOT_CONNECTED"
	DISCONNECTED = "DISCONNECTED"
	DISPOSED = "DISPOSED"
	MISSED = "MISSED"


class ReferenceDocType:
	CRM_LEAD = "CRM Lead"
	EVENT = "Event"


class _EnumValues:
	EventCallbackStatus = EventCallbackStatus
	EventCallbackCategory = EventCallbackCategory
	Roles = Roles
	LeadType = LeadType
	CallDirection = CallDirection
	CallingMethod = CallingMethod
	CallSessionStatus = CallSessionStatus
	ReferenceDocType = ReferenceDocType
	
EnumValues = _EnumValues()
