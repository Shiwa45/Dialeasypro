import os
import django
import random
from datetime import datetime, timedelta
from django.utils import timezone

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings.development")
django.setup()

from apps.tenants.models import Tenant, Domain
from apps.plans.models import Plan
from apps.authentication.models import Agent, Team, AgentTeam
from apps.leads.models import Lead, FollowUp, LeadNote, LeadActivity
from apps.calls.models import CallDisposition, CallLog
from django_tenants.utils import tenant_context

def seed():
    print("Seeding sample data...")
    
    # 1. Get or Create Plan
    plan, _ = Plan.objects.get_or_create(
        slug="growth", 
        defaults={
            "name": "Growth", 
            "price_monthly": 2499,
            "max_agents": 20,
            "max_leads": 25000,
            "max_leads_per_day": 1000
        }
    )

    # 2. Get or Create Tenant
    schema_name = "demo_corp"
    tenant, created = Tenant.objects.get_or_create(
        schema_name=schema_name,
        defaults={
            "company_name": "Demo Corp Real Estate",
            "primary_contact_name": "Rajesh Kumar",
            "primary_contact_email": "rajesh@democorp.in",
            "primary_contact_phone": "9876543210",
            "plan": plan,
            "is_active": True,
            "total_agents": 0,
            "total_leads": 0,
            "total_calls_today": 0,
        }
    )
    if created:
        Domain.objects.get_or_create(
            domain="demo.localhost",
            tenant=tenant,
            is_primary=True
        )
        print(f"Created new tenant: {schema_name}")
    else:
        print(f"Using existing tenant: {schema_name}")

    # Enter Tenant Context
    with tenant_context(tenant):
        print(f"Switched to schema: {tenant.schema_name}")
        
        # 3. Create Teams
        sales_team, _ = Team.objects.get_or_create(name="Inside Sales", defaults={"description": "Primary sales team"})
        support_team, _ = Team.objects.get_or_create(name="Customer Support", defaults={"description": "Post-sales support"})

        # 4. Create Agents
        agents_data = [
            {"email": "agent1@democorp.in", "name": "Amit Sharma", "role": "AGENT", "team": sales_team},
            {"email": "agent2@democorp.in", "name": "Priya Singh", "role": "AGENT", "team": sales_team},
            {"email": "manager@democorp.in", "name": "Neha Gupta", "role": "MANAGER", "team": sales_team, "is_team_lead": True},
            {"email": "admin@democorp.in", "name": "Rajesh Kumar", "role": "ADMIN", "is_tenant_admin": True},
        ]
        
        agents = []
        for ad in agents_data:
            agent, created = Agent.objects.get_or_create(
                email=ad["email"],
                defaults={
                    "name": ad["name"],
                    "role": ad["role"],
                    "is_tenant_admin": ad.get("is_tenant_admin", False),
                    "phone": f"99900011{len(agents)}",
                    "is_active": True,
                }
            )
            if created:
                agent.set_password("password123")
                agent.save()
            agents.append(agent)
            
            if "team" in ad:
                AgentTeam.objects.get_or_create(
                    agent=agent, team=ad["team"], defaults={"is_team_lead": ad.get("is_team_lead", False)}
                )

        print(f"Created {len(agents)} agents.")

        # 5. Create Leads
        sources = ["Facebook Ads", "Google Ads", "Organic", "Referral", "JustDial"]
        statuses = ["NEW", "CONTACTED", "INTERESTED", "NEGOTIATING", "WON", "LOST"]
        cities = ["Mumbai", "Delhi", "Bangalore", "Pune", "Hyderabad"]
        
        if Lead.objects.count() < 50:
            print("Generating 50 sample leads...")
            leads_to_create = []
            for i in range(1, 51):
                agent = random.choice([agents[0], agents[1], agents[2]])
                status = random.choice(statuses)
                
                lead = Lead(
                    name=f"Lead Customer {i}",
                    phone=f"9{random.randint(100000000, 999999999)}",
                    email=f"customer{i}@example.com",
                    city=random.choice(cities),
                    source=random.choice(sources),
                    status=status,
                    priority=random.choice(["HOT", "WARM", "COLD"]),
                    budget=random.choice([5000000, 7500000, 10000000, 15000000]),
                    score=random.randint(10, 100),
                    assigned_to=agent,
                    assigned_at=timezone.now() - timedelta(days=random.randint(0, 10)),
                )
                leads_to_create.append(lead)
            
            Lead.objects.bulk_create(leads_to_create)
        
        leads = list(Lead.objects.all()[:20])

        # 6. Create Followups & Notes for first 20 leads
        if FollowUp.objects.count() == 0:
            print("Creating Followups and Notes...")
            for lead in leads:
                # Note
                LeadNote.objects.create(
                    lead=lead,
                    agent=lead.assigned_to,
                    content=f"Initial discussion with {lead.name}. Seems interested in properties in {lead.city}."
                )
                
                # FollowUp
                FollowUp.objects.create(
                    lead=lead,
                    assigned_to=lead.assigned_to,
                    followup_type="CALL",
                    scheduled_at=timezone.now() + timedelta(days=random.randint(1, 5)),
                    notes="Discuss pricing and send brochure."
                )
                
                # Activity
                LeadActivity.objects.create(
                    lead=lead,
                    activity_type="status_change",
                    description=f"Status changed to {lead.status}",
                    performed_by=lead.assigned_to
                )

        # 7. Create Call Dispositions
        disp_names = ["Connected", "Busy", "Not Reachable", "Wrong Number", "Callback Requested"]
        dispositions = []
        for i, name in enumerate(disp_names):
            d, _ = CallDisposition.objects.get_or_create(
                slug=name.lower().replace(" ", "_"),
                defaults={
                    "name": name,
                    "is_positive": name in ["Connected", "Callback Requested"],
                    "sort_order": i
                }
            )
            dispositions.append(d)

        # 8. Create CallLogs
        if CallLog.objects.count() == 0:
            print("Creating Call Logs...")
            for lead in leads[:10]:
                CallLog.objects.create(
                    agent=lead.assigned_to,
                    lead=lead,
                    direction="OUTBOUND",
                    phone_number=lead.phone,
                    started_at=timezone.now() - timedelta(hours=random.randint(1, 48)),
                    duration_seconds=random.randint(30, 300),
                    is_connected=True,
                    disposition=dispositions[0],
                    notes="Good conversation."
                )

        # 9. Back-office module masters
        #
        # A fresh tenant with the HRMS or Recruitment module and none of these
        # is unusable on first open: no leave types means nobody can apply for
        # leave, and no pipeline stages means no candidate can be applied to a
        # role at all. Seeding them is what makes the modules work out of the box.
        seed_backoffice()

    print("✅ Sample data seeding complete!")
    print(f"Tenant Domain: http://demo.localhost:8000/crm/")
    print(f"Tenant Admin Login: admin@democorp.in / password123")
    print(f"Agent Login: agent1@democorp.in / password123")

def seed_backoffice():
    """Masters for the HRMS, Sales & Billing and Recruitment modules."""
    from decimal import Decimal

    from apps.hrms.models import Holiday, IncentiveRule, LeaveType
    from apps.recruitment.services.pipeline import seed_pipeline

    # ---- Leave types ----
    leave_types = [
        {"name": "Casual Leave",   "annual_quota_days": Decimal("12.0"), "is_paid": True,  "carry_forward": False},
        {"name": "Sick Leave",     "annual_quota_days": Decimal("6.0"),  "is_paid": True,  "carry_forward": False},
        {"name": "Earned Leave",   "annual_quota_days": Decimal("15.0"), "is_paid": True,  "carry_forward": True},
        {"name": "Loss of Pay",    "annual_quota_days": Decimal("0.0"),  "is_paid": False, "carry_forward": False},
    ]
    for lt in leave_types:
        LeaveType.objects.get_or_create(name=lt["name"], defaults=lt)
    print(f"Leave types: {LeaveType.objects.count()}")

    # ---- Holidays (national, so they hold for any Indian tenant) ----
    year = timezone.localdate().year
    holidays = [
        (f"{year}-01-26", "Republic Day"),
        (f"{year}-08-15", "Independence Day"),
        (f"{year}-10-02", "Gandhi Jayanti"),
    ]
    for iso, name in holidays:
        Holiday.objects.get_or_create(date=iso, defaults={"name": name})
    print(f"Holidays: {Holiday.objects.count()}")

    # ---- One incentive rule, so the engine has something to compute ----
    IncentiveRule.objects.get_or_create(
        name="Conversion bonus",
        defaults={
            "metric": "converted_leads",
            "per_unit_amount": Decimal("500.00"),
            "min_units": Decimal("5"),
            "applies_to_roles": ["agent", "senior_agent"],
            "is_active": True,
        },
    )
    print(f"Incentive rules: {IncentiveRule.objects.count()}")

    # ---- Recruitment pipeline ----
    created = seed_pipeline()
    print(f"Pipeline stages: {'seeded ' + str(created) if created else 'already present'}")


if __name__ == '__main__':
    seed()
