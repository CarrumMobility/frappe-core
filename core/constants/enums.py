class _EventCallbackStatus:
	SCHEDULED = "Scheduled"
	TRIGGERED = "Triggered"
	COMPLETED = "Completed"
	MISSED = "Missed"
	OVERRIDE = "Override"

class _EventCallbackCategory:
	CALLBACK = "Callback"
	VISIT_DATE = "Visit Date"

class _Roles:
	SYSTEM_USER = "System User"
	GUEST = "Guest"
	HUB_MANAGER = "Hub Manager"
	TELECALLER = "Telecaller"
	TELECALLER_LEAD = "Telecaller Lead"
	ONBOARDING = "Onboarding"
	DRIVER_MANAGER = "Driver Manager"

class _LeadType:
	LEAD = "LEAD"
	DRIVER = "DRIVER"

class _CallDirection:
	INBOUND = "INBOUND"
	OUTBOUND = "OUTBOUND"

class _CallingMethod:
	Dialer = "Dialer"
	Click2Call = "Click2Call"

class _CallSessionStatus:
	INITIATED = "INITIATED"
	FAILED = "FAILED"
	AGENT_CONNECTED = "AGENT_CONNECTED"
	CUSTOMER_CONNECTED = "CUSTOMER_CONNECTED"
	NOT_CONNECTED = "NOT_CONNECTED"
	DISCONNECTED = "DISCONNECTED"
	DISPOSED = "DISPOSED"
	MISSED = "MISSED"


class _ReferenceDocType:
	CRM_LEAD = "CRM Lead"
	EVENT = "Event"
	ROLE = "Role"
	CUSTOM_DOC_PERM = "Custom DocPerm"
	CALL_SESSION = "Call Session"
	CRM_LEAD_STATUS = "CRM Lead Status"

class _OLD_SYSTEM_DRIVER_STATUS:
	CREATED = 'created'
	TO_ONBOARD = 'to_onboard'
	ONBOARDING_DROP = 'onboarding_drop'
	ONBOARDED = 'onboarded'
	INACTIVE = 'inactive'
	RECOVERY_INITIATED = 'recovery_initiated'
	RECOVERY_DONE = 'recovered'
	TEMP_DROP = 'temp_drop'
	PERMANENT_DROP = 'permanent_drop'
	MAINTENANCE_DROP = 'maintenance_drop'
	DRIVER_RETURNED = 'driver_returned'

class _DispositionTiming:
	IMMEDIATE = "IMMEDIATE"
	LATE = "LATE"

class _LEAD_ACTION_LIST:
	RAISE_DRIVER_RETURN_REQUEST = "Raise Driver Return Request"


class _EnumValues:
	EventCallbackStatus = _EventCallbackStatus
	EventCallbackCategory = _EventCallbackCategory
	Roles = _Roles
	LeadType = _LeadType
	CallDirection = _CallDirection
	CallingMethod = _CallingMethod
	CallSessionStatus = _CallSessionStatus
	ReferenceDocType = _ReferenceDocType
	OLD_SYSTEM_DRIVER_STATUS = _OLD_SYSTEM_DRIVER_STATUS
	DispositionTiming = _DispositionTiming
	LEAD_ACTION_LIST = _LEAD_ACTION_LIST

EnumValues = _EnumValues()
