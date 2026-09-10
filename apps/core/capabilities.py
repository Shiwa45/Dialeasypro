"""
TeleCRM Backend — apps/core/capabilities.py

One declarative table saying which roles may do which business action.

Why this exists
---------------
Before this, module access was decided by two coarse permission classes
(`IsTenantAdmin`, `IsManagerOrAdmin`). That made "let someone run payroll"
indistinguishable from "let someone read every lead, reset agent passwords and
change tenant settings" — the only way to grant the first was to grant the
second. The back-office roles (HR, Accounts) exist precisely to break that
coupling, and a role list per action is the smallest thing that expresses it.

Capabilities are about ROLE. Plan entitlement is a separate axis, still handled
by `HasFeatureAccess` / `ModuleKey`. A view normally declares both:

    permission_classes = [IsAuthenticatedAgent, HasFeatureAccess, HasCapability]
    required_feature = FeatureKey.HRMS_PAYROLL      # did the tenant buy it?
    required_capability = Cap.HRMS_PAYROLL          # may this user do it?

Naming: "<module>.<action>". `view` is read-only, `manage` is create/edit/delete
of that module's masters, and anything narrower gets its own key so it can be
moved without disturbing the rest.

The same table is served to the web client at GET /api/v1/auth/capabilities/,
so a hidden button and a refused request always have the same cause — the UI
never has to re-derive the rule and drift out of sync.
"""
from apps.core.constants import AgentRole as R


class Cap:
    """Capability keys. Mirrored in the web app's hooks/useCapabilities.ts."""

    # ---- CRM core ------------------------------------------
    CRM_VIEW = "crm.view"
    CRM_MANAGE_AGENTS = "crm.manage_agents"
    CRM_SETTINGS = "crm.settings"

    # ---- HRMS ----------------------------------------------
    HRMS_VIEW = "hrms.view"              # sees own rows at minimum
    HRMS_VIEW_ALL = "hrms.view_all"      # sees the whole org's rows
    HRMS_MANAGE = "hrms.manage"          # employees, holidays, leave types, config
    HRMS_APPROVE = "hrms.approve"        # approve/reject leave and expenses
    HRMS_PAYROLL = "hrms.payroll"        # salary structures, payroll runs, payslips
    HRMS_INCENTIVES = "hrms.incentives"  # incentive rules and computation

    # ---- Sales & Billing (ERP) -----------------------------
    ERP_VIEW = "erp.view"
    ERP_MANAGE = "erp.manage"                  # customers, products, quotations, orders
    ERP_INVOICE_ISSUE = "erp.invoice_issue"    # issue an invoice (assigns a GST number)
    ERP_INVOICE_CANCEL = "erp.invoice_cancel"  # cancel an issued invoice
    ERP_PAYMENTS = "erp.payments"              # record a payment against an invoice
    ERP_EXPORT = "erp.export"                  # Tally / GST summary exports

    # ---- Recruitment (ATS) ---------------------------------
    ATS_VIEW = "ats.view"
    ATS_MANAGE = "ats.manage"          # openings, candidates, pipeline config
    ATS_INTERVIEW = "ats.interview"    # schedule interviews, submit feedback
    ATS_OFFER = "ats.offer"            # create/send offers, convert a hire to an employee


# ------------------------------------------------------------
# The table. Order within a list is irrelevant; membership is the rule.
# ------------------------------------------------------------
CAPABILITIES: dict[str, list[str]] = {
    # CRM core — unchanged from the behaviour that shipped before this table.
    Cap.CRM_VIEW: [R.ADMIN, R.MANAGER, R.SENIOR_AGENT, R.AGENT, R.READONLY,
                   R.HR, R.ACCOUNTS],
    Cap.CRM_MANAGE_AGENTS: [R.ADMIN, R.MANAGER],
    Cap.CRM_SETTINGS: [R.ADMIN],

    # HRMS. Every agent may see their own attendance, leave and payslips —
    # scoping to "own" is done by apps/hrms/permissions.scope_to_visible,
    # which keys off HRMS_VIEW_ALL.
    Cap.HRMS_VIEW: [R.ADMIN, R.HR, R.MANAGER, R.SENIOR_AGENT, R.AGENT, R.READONLY],
    Cap.HRMS_VIEW_ALL: [R.ADMIN, R.HR, R.MANAGER],
    Cap.HRMS_MANAGE: [R.ADMIN, R.HR],
    Cap.HRMS_APPROVE: [R.ADMIN, R.HR, R.MANAGER],
    # Payroll stays tight: a manager must not read a colleague's salary.
    Cap.HRMS_PAYROLL: [R.ADMIN, R.HR],
    Cap.HRMS_INCENTIVES: [R.ADMIN, R.HR],

    # Sales & Billing. Agents may read invoices for the customers they sell to;
    # only Accounts/Admin may issue or cancel one, because both actions move
    # statutory GST numbering that cannot be un-moved.
    Cap.ERP_VIEW: [R.ADMIN, R.ACCOUNTS, R.MANAGER, R.SENIOR_AGENT, R.AGENT, R.READONLY],
    Cap.ERP_MANAGE: [R.ADMIN, R.ACCOUNTS, R.MANAGER],
    Cap.ERP_INVOICE_ISSUE: [R.ADMIN, R.ACCOUNTS],
    Cap.ERP_INVOICE_CANCEL: [R.ADMIN, R.ACCOUNTS],
    Cap.ERP_PAYMENTS: [R.ADMIN, R.ACCOUNTS],
    Cap.ERP_EXPORT: [R.ADMIN, R.ACCOUNTS],

    # Recruitment. Interviewers are deliberately wider than managers — a senior
    # agent is often the person who takes the technical round, and they need to
    # file a scorecard without being able to see salary bands or offers.
    Cap.ATS_VIEW: [R.ADMIN, R.HR, R.MANAGER],
    Cap.ATS_MANAGE: [R.ADMIN, R.HR],
    Cap.ATS_INTERVIEW: [R.ADMIN, R.HR, R.MANAGER, R.SENIOR_AGENT],
    Cap.ATS_OFFER: [R.ADMIN, R.HR],
}

ALL_CAPABILITIES = list(CAPABILITIES.keys())


def has_capability(agent, capability: str) -> bool:
    """
    True when `agent`'s role is allowed to perform `capability`.

    Unknown capability keys return False rather than raising: a typo in a view
    should fail closed, and it will be obvious the first time the endpoint 403s.
    """
    role = getattr(agent, "role", None)
    if not role:
        return False
    return role in CAPABILITIES.get(capability, ())


def capabilities_for(agent) -> dict[str, bool]:
    """The full capability map for one agent, for the /auth/capabilities/ payload."""
    role = getattr(agent, "role", None)
    return {cap: (role in roles) for cap, roles in CAPABILITIES.items()}
