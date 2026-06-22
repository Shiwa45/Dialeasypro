"""
TeleCRM Backend — apps/core/constants.py

Central constants, enumerations, and choices for the entire platform.
Feature keys used in Plan features, industry choices, lead sources, etc.

IMPORTANT: When adding a new feature key, also update:
  - apps/plans/admin.py (plan feature admin display)
  - TEMPLATES_LIST.md (if it affects UI)
  - apps/core/middleware.py (feature flag injection)
"""

# ============================================================
# Feature Keys — Used in PlanFeature model
# These keys gate features per-plan for each tenant
# ============================================================

class FeatureKey:
    """
    String constants for plan feature gates.
    Usage: tenant.has_feature(FeatureKey.BULK_WHATSAPP)
    """

    # ---- Lead Source Integrations --------------------------
    INDIAMART = "indiamart"
    META_LEAD_ADS = "meta_lead_ads"
    NINETYNINEACRES = "99acres"
    HOUSING_COM = "housing_com"
    MAGICBRICKS = "magicbricks"
    JUSTDIAL = "justdial"
    SULEKHA = "sulekha"
    TRADEINDIA = "tradeindia"
    GOOGLE_ADS_LEADS = "google_ads_leads"
    WEBSITE_WIDGET = "website_widget"
    GENERIC_WEBHOOK = "generic_webhook"
    OUTBOUND_WEBHOOK = "outbound_webhook"
    ZAPIER_INTEGRATION = "zapier_integration"

    # ---- Communication Features ----------------------------
    WHATSAPP_SINGLE_PROVIDER = "whatsapp_single"
    WHATSAPP_MULTI_PROVIDER = "whatsapp_multi"
    BULK_WHATSAPP = "bulk_whatsapp"
    BULK_EMAIL = "bulk_email"
    BULK_SMS = "bulk_sms"
    ONE_CLICK_WHATSAPP = "one_click_whatsapp"
    ONE_CLICK_EMAIL = "one_click_email"
    ONE_CLICK_SMS = "one_click_sms"
    EMAIL_CAMPAIGNS = "email_campaigns"
    SMS_CAMPAIGNS = "sms_campaigns"
    WHATSAPP_INCOMING = "whatsapp_incoming"

    # ---- Call Features -------------------------------------
    CALL_RECORDING_ACCESS = "call_recording_access"
    CALL_RECORDING_DOWNLOAD = "call_recording_download"
    CLOUD_TELEPHONY = "cloud_telephony"
    AUTO_DIALER = "auto_dialer"

    # ---- CRM Features --------------------------------------
    CUSTOM_FIELDS = "custom_fields"
    LEAD_SCORING = "lead_scoring"
    LEAD_PIPELINE = "lead_pipeline"
    LEAD_IMPORT = "lead_import"
    LEAD_EXPORT = "lead_export"
    FOLLOW_UP_AUTOMATION = "followup_automation"
    CONTACT_HISTORY = "contact_history"

    # ---- Agent & Team Features -----------------------------
    TEAM_MANAGEMENT = "team_management"
    AGENT_MONITORING = "agent_monitoring"
    AGENT_GPS_TRACKING = "agent_gps_tracking"
    AGENT_PERFORMANCE_REPORTS = "agent_performance"

    # ---- Reports & Analytics -------------------------------
    BASIC_REPORTS = "basic_reports"
    ADVANCED_REPORTS = "advanced_reports"
    SCHEDULED_REPORTS = "scheduled_reports"
    CUSTOM_DASHBOARDS = "custom_dashboards"

    # ---- API & Integrations --------------------------------
    API_ACCESS = "api_access"

    # ---- Platform Features ---------------------------------
    WHITE_LABEL = "white_label"
    PRIORITY_SUPPORT = "priority_support"

    # All feature keys as a list (for validation)
    ALL = [
        INDIAMART, META_LEAD_ADS, NINETYNINEACRES, HOUSING_COM, MAGICBRICKS,
        JUSTDIAL, SULEKHA, TRADEINDIA, GOOGLE_ADS_LEADS, WEBSITE_WIDGET,
        GENERIC_WEBHOOK, OUTBOUND_WEBHOOK, ZAPIER_INTEGRATION,
        WHATSAPP_SINGLE_PROVIDER, WHATSAPP_MULTI_PROVIDER, BULK_WHATSAPP,
        BULK_EMAIL, BULK_SMS, ONE_CLICK_WHATSAPP, ONE_CLICK_EMAIL, ONE_CLICK_SMS,
        EMAIL_CAMPAIGNS, SMS_CAMPAIGNS, WHATSAPP_INCOMING,
        CALL_RECORDING_ACCESS, CALL_RECORDING_DOWNLOAD, CLOUD_TELEPHONY, AUTO_DIALER,
        CUSTOM_FIELDS, LEAD_SCORING, LEAD_PIPELINE, LEAD_IMPORT, LEAD_EXPORT,
        FOLLOW_UP_AUTOMATION, CONTACT_HISTORY,
        TEAM_MANAGEMENT, AGENT_MONITORING, AGENT_GPS_TRACKING, AGENT_PERFORMANCE_REPORTS,
        BASIC_REPORTS, ADVANCED_REPORTS, SCHEDULED_REPORTS, CUSTOM_DASHBOARDS,
        API_ACCESS, WHITE_LABEL, PRIORITY_SUPPORT,
    ]

    # Human-readable labels
    LABELS = {
        INDIAMART: "IndiaMART Integration",
        META_LEAD_ADS: "Meta (Facebook/Instagram) Lead Ads",
        NINETYNINEACRES: "99acres Integration",
        HOUSING_COM: "Housing.com Integration",
        MAGICBRICKS: "MagicBricks Integration",
        JUSTDIAL: "JustDial Integration",
        SULEKHA: "Sulekha Integration",
        TRADEINDIA: "TradeIndia Integration",
        GOOGLE_ADS_LEADS: "Google Ads Lead Forms",
        WEBSITE_WIDGET: "Website Lead Widget",
        GENERIC_WEBHOOK: "Generic Inbound Webhook",
        OUTBOUND_WEBHOOK: "Outbound Webhook (push to external CRM)",
        ZAPIER_INTEGRATION: "Zapier / Make.com Integration",
        WHATSAPP_SINGLE_PROVIDER: "WhatsApp Business (Single Provider)",
        WHATSAPP_MULTI_PROVIDER: "WhatsApp Business (Multiple Providers)",
        BULK_WHATSAPP: "Bulk WhatsApp Campaigns",
        BULK_EMAIL: "Bulk Email Campaigns",
        BULK_SMS: "Bulk SMS Campaigns",
        ONE_CLICK_WHATSAPP: "One-Click WhatsApp",
        ONE_CLICK_EMAIL: "One-Click Email",
        ONE_CLICK_SMS: "One-Click SMS",
        EMAIL_CAMPAIGNS: "Email Campaign Management",
        SMS_CAMPAIGNS: "SMS Campaign Management",
        WHATSAPP_INCOMING: "Incoming WhatsApp Messages",
        CALL_RECORDING_ACCESS: "Call Recording Access (Play)",
        CALL_RECORDING_DOWNLOAD: "Call Recording Download",
        CLOUD_TELEPHONY: "Cloud Telephony (Exotel/Knowlarity)",
        AUTO_DIALER: "Auto-Dialer (Mobile App)",
        CUSTOM_FIELDS: "Custom CRM Fields",
        LEAD_SCORING: "Lead Scoring",
        LEAD_PIPELINE: "Lead Pipeline / Funnel View",
        LEAD_IMPORT: "Lead Import (CSV/Excel)",
        LEAD_EXPORT: "Lead Export (CSV/Excel)",
        FOLLOW_UP_AUTOMATION: "Follow-up Automation Rules",
        CONTACT_HISTORY: "Full Contact History",
        TEAM_MANAGEMENT: "Team Management",
        AGENT_MONITORING: "Real-time Agent Monitoring",
        AGENT_GPS_TRACKING: "Agent GPS Tracking",
        AGENT_PERFORMANCE_REPORTS: "Agent Performance Reports",
        BASIC_REPORTS: "Basic Reports",
        ADVANCED_REPORTS: "Advanced Analytics & Reports",
        SCHEDULED_REPORTS: "Scheduled Email Reports",
        CUSTOM_DASHBOARDS: "Custom Dashboards",
        API_ACCESS: "REST API Access",
        WHITE_LABEL: "White-label Branding",
        PRIORITY_SUPPORT: "Priority Support",
    }

    # Feature choices for Django model field
    CHOICES = [(key, label) for key, label in LABELS.items()]


# ============================================================
# Plan Choices
# ============================================================

class PlanSlug:
    STARTER = "starter"
    GROWTH = "growth"
    BUSINESS = "business"
    ENTERPRISE = "enterprise"
    CUSTOM = "custom"

    CHOICES = [
        (STARTER, "Starter"),
        (GROWTH, "Growth"),
        (BUSINESS, "Business"),
        (ENTERPRISE, "Enterprise"),
        (CUSTOM, "Custom"),
    ]


# ============================================================
# Subscription Status Choices
# ============================================================

class SubscriptionStatus:
    TRIAL = "trial"
    ACTIVE = "active"
    PAST_DUE = "past_due"
    PAUSED = "paused"
    CANCELLED = "cancelled"
    SUSPENDED = "suspended"

    CHOICES = [
        (TRIAL, "Trial"),
        (ACTIVE, "Active"),
        (PAST_DUE, "Past Due"),
        (PAUSED, "Paused"),
        (CANCELLED, "Cancelled"),
        (SUSPENDED, "Suspended"),
    ]

    # Tenants in these statuses can use the platform
    ACTIVE_STATUSES = [TRIAL, ACTIVE]


# ============================================================
# Industry Choices (Indian market focused)
# ============================================================

class Industry:
    REAL_ESTATE = "real_estate"
    EDTECH = "edtech"
    BFSI = "bfsi"
    INSURANCE = "insurance"
    AUTOMOBILE = "automobile"
    MANUFACTURING = "manufacturing"
    IT_SERVICES = "it_services"
    HEALTHCARE = "healthcare"
    ECOMMERCE = "ecommerce"
    STAFFING = "staffing"
    RETAIL = "retail"
    HOSPITALITY = "hospitality"
    EDUCATION = "education"
    OTHER = "other"

    CHOICES = [
        (REAL_ESTATE, "Real Estate"),
        (EDTECH, "EdTech / Online Education"),
        (BFSI, "Banking, Financial Services & Insurance (BFSI)"),
        (INSURANCE, "Insurance"),
        (AUTOMOBILE, "Automobile / Auto Dealership"),
        (MANUFACTURING, "Manufacturing / B2B"),
        (IT_SERVICES, "IT Services / SaaS"),
        (HEALTHCARE, "Healthcare"),
        (ECOMMERCE, "E-Commerce / D2C"),
        (STAFFING, "Staffing / Recruitment"),
        (RETAIL, "Retail"),
        (HOSPITALITY, "Hospitality / Travel"),
        (EDUCATION, "Education / Institute"),
        (OTHER, "Other"),
    ]


# ============================================================
# Agent Roles
# ============================================================

class AgentRole:
    ADMIN = "admin"          # Full tenant access (same as tenant admin)
    MANAGER = "manager"      # Manage team, view team reports
    SENIOR_AGENT = "senior_agent"  # Own leads + junior agents' leads
    AGENT = "agent"          # Own leads only
    READONLY = "readonly"    # View only access

    CHOICES = [
        (ADMIN, "Tenant Admin"),
        (MANAGER, "Manager"),
        (SENIOR_AGENT, "Senior Agent"),
        (AGENT, "Agent"),
        (READONLY, "Read Only"),
    ]

    # Roles that can manage other agents
    MANAGEMENT_ROLES = [ADMIN, MANAGER]

    # Roles that can access all leads in their team
    TEAM_ACCESS_ROLES = [ADMIN, MANAGER, SENIOR_AGENT]

    # Role hierarchy for permission checks (higher number = more access)
    HIERARCHY = {
        READONLY: 1,
        AGENT: 2,
        SENIOR_AGENT: 3,
        MANAGER: 4,
        ADMIN: 5,
    }


class AgentWorkStatus:
    """
    Live work/presence status for agent monitoring.

    Presence is tied to an auto-dial session: starting auto-dial puts the agent
    ONLINE (available); exiting the dialer (or a stale heartbeat) makes them
    OFFLINE. During a session the status cycles available → on_call → wrap_up,
    with break as a manual toggle (only between calls).
    """

    OFFLINE = "offline"      # Not in an auto-dial session
    AVAILABLE = "available"  # Session active, waiting/between calls
    ON_CALL = "on_call"      # Call connected
    WRAP_UP = "wrap_up"      # Call ended, disposing (after-call work)
    BREAK = "break"          # Manual break

    CHOICES = [
        (OFFLINE, "Offline"),
        (AVAILABLE, "Available"),
        (ON_CALL, "On Call"),
        (WRAP_UP, "Wrap-up"),
        (BREAK, "Break"),
    ]

    # Statuses that count as "online" (in an active session)
    ONLINE_STATUSES = [AVAILABLE, ON_CALL, WRAP_UP, BREAK]

    # Valid statuses an agent client may report
    REPORTABLE = [OFFLINE, AVAILABLE, ON_CALL, WRAP_UP, BREAK]


# ============================================================
# Lead Source Choices
# ============================================================

class LeadSource:
    INDIAMART = "indiamart"
    META_FACEBOOK = "meta_facebook"
    META_INSTAGRAM = "meta_instagram"
    NINETYNINEACRES = "99acres"
    HOUSING_COM = "housing_com"
    MAGICBRICKS = "magicbricks"
    JUSTDIAL = "justdial"
    SULEKHA = "sulekha"
    TRADEINDIA = "tradeindia"
    GOOGLE_ADS = "google_ads"
    WEBSITE = "website"
    WEBHOOK = "webhook"
    MANUAL = "manual"
    CSV_IMPORT = "csv_import"
    API = "api"
    WHATSAPP = "whatsapp"
    REFERRAL = "referral"

    CHOICES = [
        (INDIAMART, "IndiaMART"),
        (META_FACEBOOK, "Meta - Facebook Lead Ads"),
        (META_INSTAGRAM, "Meta - Instagram Lead Ads"),
        (NINETYNINEACRES, "99acres"),
        (HOUSING_COM, "Housing.com"),
        (MAGICBRICKS, "MagicBricks"),
        (JUSTDIAL, "JustDial"),
        (SULEKHA, "Sulekha"),
        (TRADEINDIA, "TradeIndia"),
        (GOOGLE_ADS, "Google Ads Lead Forms"),
        (WEBSITE, "Website Widget"),
        (WEBHOOK, "Webhook"),
        (MANUAL, "Manual Entry"),
        (CSV_IMPORT, "CSV Import"),
        (API, "API"),
        (WHATSAPP, "WhatsApp Inbound"),
        (REFERRAL, "Referral"),
    ]

    # Lead sources that require specific feature flags
    FEATURE_MAP = {
        INDIAMART: FeatureKey.INDIAMART,
        META_FACEBOOK: FeatureKey.META_LEAD_ADS,
        META_INSTAGRAM: FeatureKey.META_LEAD_ADS,
        NINETYNINEACRES: FeatureKey.NINETYNINEACRES,
        HOUSING_COM: FeatureKey.HOUSING_COM,
        MAGICBRICKS: FeatureKey.MAGICBRICKS,
        JUSTDIAL: FeatureKey.JUSTDIAL,
        SULEKHA: FeatureKey.SULEKHA,
        TRADEINDIA: FeatureKey.TRADEINDIA,
        GOOGLE_ADS: FeatureKey.GOOGLE_ADS_LEADS,
        WEBSITE: FeatureKey.WEBSITE_WIDGET,
        WEBHOOK: FeatureKey.GENERIC_WEBHOOK,
    }


# ============================================================
# Lead Status Choices
# ============================================================

class LeadStatus:
    NEW = "new"
    ATTEMPTED = "attempted"
    CONTACTED = "contacted"
    INTERESTED = "interested"
    NOT_INTERESTED = "not_interested"
    FOLLOW_UP = "follow_up"
    NEGOTIATION = "negotiation"    # Active deal in negotiation stage
    CONVERTED = "converted"
    WON = "converted"              # Alias: WON == CONVERTED (same DB value)
    LOST = "lost"
    DUPLICATE = "duplicate"

    CHOICES = [
        (NEW, "New"),
        (ATTEMPTED, "Attempted"),
        (CONTACTED, "Contacted"),
        (INTERESTED, "Interested"),
        (NOT_INTERESTED, "Not Interested"),
        (FOLLOW_UP, "Follow-up Scheduled"),
        (NEGOTIATION, "In Negotiation"),
        (CONVERTED, "Converted / Won"),
        (LOST, "Lost"),
        (DUPLICATE, "Duplicate"),
    ]

    # Final statuses (no further action needed)
    FINAL_STATUSES = [CONVERTED, LOST, DUPLICATE]

    # Active statuses (leads to work on — shown in pipeline board)
    ACTIVE_STATUSES = [NEW, ATTEMPTED, CONTACTED, INTERESTED, FOLLOW_UP, NEGOTIATION]


# ============================================================
# Lead Priority
# ============================================================

class LeadPriority:
    HOT = "hot"
    WARM = "warm"
    COLD = "cold"

    CHOICES = [
        (HOT, "Hot 🔥"),
        (WARM, "Warm 🌤"),
        (COLD, "Cold ❄️"),
    ]


# ============================================================
# Call Direction
# ============================================================

class CallDirection:
    OUTBOUND = "outbound"
    INBOUND = "inbound"
    MISSED = "missed"

    CHOICES = [
        (OUTBOUND, "Outbound"),
        (INBOUND, "Inbound"),
        (MISSED, "Missed"),
    ]


# ============================================================
# Follow-Up Type
# ============================================================

class FollowUpType:
    CALL = "call"
    WHATSAPP = "whatsapp"
    EMAIL = "email"
    SITE_VISIT = "site_visit"
    MEETING = "meeting"
    DEMO = "demo"
    OTHER = "other"

    CHOICES = [
        (CALL, "Call"),
        (WHATSAPP, "WhatsApp"),
        (EMAIL, "Email"),
        (SITE_VISIT, "Site Visit"),
        (MEETING, "Meeting"),
        (DEMO, "Demo"),
        (OTHER, "Other"),
    ]


# ============================================================
# WhatsApp Provider Keys
# ============================================================

class WhatsAppProvider:
    WATI = "wati"
    INTERAKT = "interakt"
    GUPSHUP = "gupshup"
    AISENSY = "aisensy"
    TWILIO = "twilio"
    META_CLOUD = "meta_cloud"
    THREE_SIXTY_DIALOG = "360dialog"

    CHOICES = [
        (WATI, "WATI"),
        (INTERAKT, "Interakt"),
        (GUPSHUP, "Gupshup"),
        (AISENSY, "AiSensy"),
        (TWILIO, "Twilio"),
        (META_CLOUD, "Meta Cloud API (Direct)"),
        (THREE_SIXTY_DIALOG, "360dialog"),
    ]


# ============================================================
# Audit Log Actions
# ============================================================

class AuditAction:
    CREATE = "create"
    UPDATE = "update"
    DELETE = "delete"
    LOGIN = "login"
    LOGOUT = "logout"
    LOGIN_FAILED = "login_failed"
    IMPERSONATE = "impersonate"
    PLAN_CHANGE = "plan_change"
    SUSPEND = "suspend"
    ACTIVATE = "activate"
    EXPORT = "export"
    IMPORT = "import"
    BULK_ACTION = "bulk_action"
    SETTINGS_CHANGE = "settings_change"
    PASSWORD_CHANGE = "password_change"
    PASSWORD_RESET = "password_reset"

    CHOICES = [
        (CREATE, "Create"),
        (UPDATE, "Update"),
        (DELETE, "Delete"),
        (LOGIN, "Login"),
        (LOGOUT, "Logout"),
        (LOGIN_FAILED, "Login Failed"),
        (IMPERSONATE, "Impersonate"),
        (PLAN_CHANGE, "Plan Change"),
        (SUSPEND, "Suspend"),
        (ACTIVATE, "Activate"),
        (EXPORT, "Export"),
        (IMPORT, "Import"),
        (BULK_ACTION, "Bulk Action"),
        (SETTINGS_CHANGE, "Settings Change"),
        (PASSWORD_CHANGE, "Password Change"),
        (PASSWORD_RESET, "Password Reset"),
    ]


# ============================================================
# GST Configuration (India)
# ============================================================

class GSTState:
    """State codes and GST rates for Indian GST calculation."""

    # States subject to IGST (inter-state supply)
    TELECRM_STATE = "MH"  # TeleCRM's registered state (Maharashtra — update to actual)
    GST_RATE = 18  # 18% GST on SaaS

    # HSN/SAC code for SaaS services
    SAC_CODE = "998315"  # Information technology software services

    @classmethod
    def get_gst_components(cls, customer_state: str):
        """
        Returns GST components based on customer's state vs TeleCRM's state.

        Inter-state → IGST (18%)
        Intra-state → CGST (9%) + SGST (9%)
        """
        if customer_state == cls.TELECRM_STATE:
            return {
                "cgst_rate": 9,
                "sgst_rate": 9,
                "igst_rate": 0,
                "is_interstate": False,
            }
        return {
            "cgst_rate": 0,
            "sgst_rate": 0,
            "igst_rate": 18,
            "is_interstate": True,
        }


# ============================================================
# Cache Timeout Constants (in seconds)
# ============================================================

class CacheTimeout:
    FEATURE_FLAGS = 300          # 5 minutes — tenant plan features
    AGENT_SESSION = 3600         # 1 hour — agent session data
    TENANT_STATS = 600           # 10 minutes — tenant usage stats
    PLAN_LIST = 3600             # 1 hour — public plan list
    REPORT_DATA = 300            # 5 minutes — report query results
    DND_CHECK = 86400 * 30       # 30 days — TRAI DND status per number
    INTEGRATION_STATUS = 300     # 5 minutes — integration health status


# ============================================================
# File Size Limits (in bytes)
# ============================================================

class FileSizeLimit:
    PROFILE_PHOTO = 5 * 1024 * 1024          # 5 MB
    LEAD_ATTACHMENT = 25 * 1024 * 1024       # 25 MB
    CSV_IMPORT = 50 * 1024 * 1024            # 50 MB
    CALL_RECORDING = 200 * 1024 * 1024       # 200 MB
    EMAIL_ATTACHMENT = 10 * 1024 * 1024      # 10 MB
    WHATSAPP_MEDIA = 16 * 1024 * 1024        # 16 MB (Meta limit)


# ============================================================
# Indian State Codes (for GST)
# ============================================================

INDIAN_STATES = [
    ("AN", "Andaman and Nicobar Islands"),
    ("AP", "Andhra Pradesh"),
    ("AR", "Arunachal Pradesh"),
    ("AS", "Assam"),
    ("BR", "Bihar"),
    ("CH", "Chandigarh"),
    ("CG", "Chhattisgarh"),
    ("DN", "Dadra and Nagar Haveli and Daman and Diu"),
    ("DL", "Delhi"),
    ("GA", "Goa"),
    ("GJ", "Gujarat"),
    ("HR", "Haryana"),
    ("HP", "Himachal Pradesh"),
    ("JK", "Jammu and Kashmir"),
    ("JH", "Jharkhand"),
    ("KA", "Karnataka"),
    ("KL", "Kerala"),
    ("LA", "Ladakh"),
    ("LD", "Lakshadweep"),
    ("MP", "Madhya Pradesh"),
    ("MH", "Maharashtra"),
    ("MN", "Manipur"),
    ("ML", "Meghalaya"),
    ("MZ", "Mizoram"),
    ("NL", "Nagaland"),
    ("OD", "Odisha"),
    ("PY", "Puducherry"),
    ("PB", "Punjab"),
    ("RJ", "Rajasthan"),
    ("SK", "Sikkim"),
    ("TN", "Tamil Nadu"),
    ("TS", "Telangana"),
    ("TR", "Tripura"),
    ("UP", "Uttar Pradesh"),
    ("UK", "Uttarakhand"),
    ("WB", "West Bengal"),
]
