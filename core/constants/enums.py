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
	RAISE_DRIVER_REACTIVATION_REQUEST = "Raise Driver Reactivation Request"
	REMOVE_ONBOARDING_DROP = "Remove Onboarding Drop"
	MERGE_LEAD = "Merge Lead"
	UNMERGE_LEAD = "Unmerge Lead"


class _LEAD_ACTION_SLUG:
	"""Stable API / UI ``action`` values for CRM Lead actions (driver + lead)."""

	RAISE_DRIVER_REACTIVATION_REQUEST = "raise_driver_reactivation_request"
	REMOVE_ONBOARDING_DROP = "remove_onboarding_drop"
	MERGE_LEAD = "merge_lead"
	UNMERGE_LEAD = "unmerge_lead"

class LeadStatus:
	DROP = "Drop"
	CONVERTED = "Converted"
	NEW = "New"
	NOT_ELIGIBLE= "Not Eligible"
	INTERESTED = "Interested"
	NOT_INTERESTED = "Not Interested"

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
	LEAD_ACTION_SLUG = _LEAD_ACTION_SLUG

EnumValues = _EnumValues()
