"""
TeleCRM Backend — apps/hrms/constants.py

Enumerations for the HRMS add-on module.
"""


class EmploymentType:
    FULL_TIME = "full_time"
    PART_TIME = "part_time"
    CONTRACT = "contract"
    INTERN = "intern"

    CHOICES = [
        (FULL_TIME, "Full Time"),
        (PART_TIME, "Part Time"),
        (CONTRACT, "Contract"),
        (INTERN, "Intern"),
    ]


class AttendanceStatus:
    PRESENT = "present"
    HALF_DAY = "half_day"
    ABSENT = "absent"
    ON_LEAVE = "on_leave"
    HOLIDAY = "holiday"
    WEEK_OFF = "week_off"

    CHOICES = [
        (PRESENT, "Present"),
        (HALF_DAY, "Half Day"),
        (ABSENT, "Absent"),
        (ON_LEAVE, "On Leave"),
        (HOLIDAY, "Holiday"),
        (WEEK_OFF, "Week Off"),
    ]

    # Statuses that count as a paid working day for payroll.
    PAID_STATUSES = [PRESENT, ON_LEAVE, HOLIDAY, WEEK_OFF]


class AttendanceSource:
    AUTO = "auto"      # derived from the agent's dialer session (AgentStatusLog)
    MANUAL = "manual"  # employee tapped check-in / check-out
    ADMIN = "admin"    # corrected by an admin

    CHOICES = [(AUTO, "Auto"), (MANUAL, "Manual"), (ADMIN, "Admin Correction")]


class ApprovalStatus:
    PENDING = "pending"
    APPROVED = "approved"
    REJECTED = "rejected"
    CANCELLED = "cancelled"

    CHOICES = [
        (PENDING, "Pending"),
        (APPROVED, "Approved"),
        (REJECTED, "Rejected"),
        (CANCELLED, "Cancelled"),
    ]

    OPEN_STATUSES = [PENDING]


class ExpenseCategory:
    TRAVEL = "travel"
    FOOD = "food"
    ACCOMMODATION = "accommodation"
    COMMUNICATION = "communication"
    OTHER = "other"

    CHOICES = [
        (TRAVEL, "Travel"),
        (FOOD, "Food"),
        (ACCOMMODATION, "Accommodation"),
        (COMMUNICATION, "Communication"),
        (OTHER, "Other"),
    ]


class IncentiveMetric:
    """What an incentive rule pays out on. All are read from the CRM."""

    CONVERTED_LEADS = "converted_leads"   # leads that reached status=converted
    CONNECTED_CALLS = "connected_calls"   # calls with is_connected=True
    TALK_MINUTES = "talk_minutes"         # total connected call minutes
    REVENUE = "revenue"                   # sum of converted leads' deal_value

    CHOICES = [
        (CONVERTED_LEADS, "Converted Leads"),
        (CONNECTED_CALLS, "Connected Calls"),
        (TALK_MINUTES, "Talk Minutes"),
        (REVENUE, "Revenue (deal value)"),
    ]

    # Metrics paid as a percentage of the metric value rather than per unit.
    PERCENTAGE_METRICS = [REVENUE]


class PayslipStatus:
    DRAFT = "draft"
    FINALIZED = "finalized"
    PAID = "paid"

    CHOICES = [(DRAFT, "Draft"), (FINALIZED, "Finalized"), (PAID, "Paid")]
