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
	ADMIN = "Admin"
	ADMINISTRATOR = "Administrator"

class _LeadType:
	LEAD = "LEAD"
	DRIVER = "DRIVER"

class _CallDirection:
	INBOUND = "INBOUND"
	OUTBOUND = "OUTBOUND"

class _CallingMethod:
	Dialer = "Dialer"
	Agent = "Agent"

class _CallSessionStatus:
	INITIATED = "INITIATED"
	FAILED = "FAILED"
	AGENT_CONNECTED = "AGENT_CONNECTED"
	CUSTOMER_CONNECTED = "CUSTOMER_CONNECTED"
	NOT_CONNECTED = "OB Missed"
	DISCONNECTED = "DISCONNECTED"
	DISPOSED = "DISPOSED"
	MISSED = "IB Missed"


class _ReferenceDocType:
	CRM_LEAD = "CRM Lead"
	EVENT = "Event"
	ROLE = "Role"
	CUSTOM_DOC_PERM = "Custom DocPerm"
	CALL_SESSION = "Call Session"
	CRM_LEAD_STATUS = "CRM Lead Status"
	AGENT_PERFORMANCE = "Agent Performance"
	USER = "User"
	LEAD_WALKIN_DONE = "Lead walkin done"
	LEAD_SOURCE = "CRM Lead Source"

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
	MARK_ONBOARDING_DROP = "Mark Onboarding Drop"
	MARK_WALK_IN_DONE = "Mark WalkIn Done"


class _LEAD_ACTION_SLUG:
	"""Stable API / UI ``action`` values for CRM Lead actions (driver + lead)."""

	RAISE_DRIVER_REACTIVATION_REQUEST = "raise_driver_reactivation_request"
	REMOVE_ONBOARDING_DROP = "remove_onboarding_drop"
	MARK_ONBOARDING_DROP = "mark_onboarding_drop"
	MERGE_LEAD = "merge_lead"
	UNMERGE_LEAD = "unmerge_lead"
	MARK_WALK_IN_DONE = "mark_walk_in_done"

class _LeadStatus:
	DROP = "Drop"
	CONVERTED = "Converted"
	NEW = "New"
	NOT_ELIGIBLE= "Not Eligible"
	INTERESTED = "Interested"
	NOT_INTERESTED = "Not Interested"

class _LEAD_SOURCE:
	GateApp = "Gate App"

class _HUB_VISIT_STATUS:
	NotInHub = "NOT_IN_HUB"
	InHub = "IN_HUB"
	HubVisited = "HUB_VISITED"

class _LEAD_SOURCE_PURPOSE:
	Inbound = "Inbound"
	ManualSelection = "Manual Selection"

class _CallLockEventType:
	DialerCallConnected = "dialer_call_connected"

class _CRM_FIELD_DB:
	ERP = "erp"
	PORTAL = "portal"

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
	LeadStatus = _LeadStatus
	LeadSource = _LEAD_SOURCE
	HubVisitStatus = _HUB_VISIT_STATUS
	LeadSourcePurpose = _LEAD_SOURCE_PURPOSE
	CallLockEventType = _CallLockEventType
	CRM_FIELD_DB = _CRM_FIELD_DB

EnumValues = _EnumValues()
