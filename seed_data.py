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

    print("✅ Sample data seeding complete!")
    print(f"Tenant Domain: http://demo.localhost:8000/crm/")
    print(f"Tenant Admin Login: admin@democorp.in / password123")
    print(f"Agent Login: agent1@democorp.in / password123")

if __name__ == '__main__':
    seed()
