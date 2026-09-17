# TeleCRM Database Schema\n\nThis document outlines the database schema across all apps, including public (shared) and tenant-specific models.\n\n## Tenants (apps.tenants)\n\n### Tenant\n*Table: tenants_tenant*\n> Represents one CRM client company (tenant).

    Key fields:
      schema_name   : PostgreSQL schema name. Must be unique, lowercase,
                      no spaces. Auto-set from company name at creation.
      is_active     : Master switch — if False, all logins blocked.
      plan          : FK to Plan (in plans app). May be null before subscription.

    django-tenants behaviour:
      auto_create_schema = True → Calling .save() creates the PG schema
                                   and runs all TENANT_APPS migrations.\n\n| Field | Type | Properties |\n|---|---|---|\n| domains | Reverse Relation | -> Domain |\n| subscriptions | Reverse Relation | -> Subscription |\n| invoices | Reverse Relation | -> Invoice |\n| support_notes | Reverse Relation | -> SupportNote |\n| id | BigAutoField | PK, Unique, Blank |\n| schema_name | CharField | Unique |\n| created_at | DateTimeField | Blank |\n| updated_at | DateTimeField | Blank |\n| company_name | CharField |  |\n| industry | CharField | Blank |\n| gstin | CharField | Blank |\n| billing_address | TextField | Blank |\n| city | CharField | Blank |\n| state | CharField | Blank |\n| pincode | CharField | Blank |\n| primary_contact_name | CharField |  |\n| primary_contact_email | CharField |  |\n| primary_contact_phone | CharField |  |\n| plan | ForeignKey | Nullable, Blank, FK -> Plan |\n| subscription_status | CharField |  |\n| trial_ends_at | DateTimeField | Nullable, Blank |\n| is_active | BooleanField |  |\n| onboarding_completed | BooleanField |  |\n| onboarding_step | PositiveSmallIntegerField |  |\n| logo | FileField | Nullable, Blank |\n| primary_color | CharField |  |\n| timezone | CharField |  |\n| language_preference | CharField |  |\n| custom_domain | CharField | Blank |\n| internal_notes | TextField | Blank |\n| total_agents | PositiveIntegerField |  |\n| total_leads | PositiveIntegerField |  |\n| total_calls_today | PositiveIntegerField |  |\n\n### Domain\n*Table: tenants_domain*\n> Maps a domain/subdomain to a Tenant.

    django-tenants uses this to route requests:
    1. Request hits acmerealty.telecrm.in
    2. django-tenants queries Domain for this domain
    3. Sets connection schema to tenant.schema_name
    4. Request proceeds in tenant's PostgreSQL schema

    Multiple domains can map to one tenant (e.g., custom domain + subdomain).
    Only one should have is_primary=True.\n\n| Field | Type | Properties |\n|---|---|---|\n| id | BigAutoField | PK, Unique, Blank |\n| domain | CharField | Unique |\n| tenant | ForeignKey | FK -> Tenant |\n| is_primary | BooleanField |  |\n\n## Plans (apps.plans)\n\n### Plan\n*Table: plans_plan*\n> A subscription plan tier.
    All capacity limits enforced here — agents, leads, bulk messages, storage.\n\n| Field | Type | Properties |\n|---|---|---|\n| tenants | Reverse Relation | -> Tenant |\n| features | Reverse Relation | -> PlanFeature |\n| subscriptions | Reverse Relation | -> Subscription |\n| id | BigAutoField | PK, Unique, Blank |\n| created_at | DateTimeField | Blank |\n| updated_at | DateTimeField | Blank |\n| sort_order | PositiveIntegerField |  |\n| name | CharField | Unique |\n| slug | SlugField | Unique |\n| description | TextField | Blank |\n| price_monthly | DecimalField |  |\n| price_yearly | DecimalField |  |\n| razorpay_monthly_plan_id | CharField | Blank |\n| razorpay_yearly_plan_id | CharField | Blank |\n| max_agents | PositiveIntegerField |  |\n| max_leads | PositiveIntegerField |  |\n| max_leads_per_day | PositiveIntegerField |  |\n| max_whatsapp_bulk_per_day | PositiveIntegerField |  |\n| max_email_bulk_per_day | PositiveIntegerField |  |\n| max_sms_per_day | PositiveIntegerField |  |\n| storage_gb | PositiveIntegerField |  |\n| custom_fields_limit | PositiveIntegerField |  |\n| lead_sources_limit | PositiveIntegerField |  |\n| whatsapp_templates_limit | PositiveIntegerField |  |\n| data_retention_days | PositiveIntegerField |  |\n| is_active | BooleanField |  |\n| is_public | BooleanField |  |\n\n### PlanFeature\n*Table: plans_planfeature*\n> A feature flag for a specific plan.
    Allows granular feature gating per plan tier.\n\n| Field | Type | Properties |\n|---|---|---|\n| id | BigAutoField | PK, Unique, Blank |\n| plan | ForeignKey | FK -> Plan |\n| feature_key | CharField |  |\n| is_enabled | BooleanField |  |\n\n### Subscription\n*Table: plans_subscription*\n> A tenant's subscription to a plan.
    Tracks billing status, Razorpay subscription ID, and period dates.\n\n| Field | Type | Properties |\n|---|---|---|\n| invoices | Reverse Relation | -> Invoice |\n| created_at | DateTimeField | Blank |\n| updated_at | DateTimeField | Blank |\n| id | UUIDField | PK, Unique |\n| tenant | ForeignKey | FK -> Tenant |\n| plan | ForeignKey | FK -> Plan |\n| razorpay_subscription_id | CharField | Blank |\n| razorpay_customer_id | CharField | Blank |\n| status | CharField |  |\n| billing_cycle | CharField |  |\n| current_period_start | DateTimeField | Nullable, Blank |\n| current_period_end | DateTimeField | Nullable, Blank |\n| trial_end | DateTimeField | Nullable, Blank |\n| cancel_at_period_end | BooleanField |  |\n| cancelled_at | DateTimeField | Nullable, Blank |\n\n### Invoice\n*Table: plans_invoice*\n> GST-compliant invoice for each billing event.

    Follows Indian GST rules:
    - Intra-state (same state as TeleCRM): CGST (9%) + SGST (9%)
    - Inter-state (different state): IGST (18%)
    - SAC code: 998315 (Information technology software services)
    - Invoice number format: TCRM/2024-25/00001\n\n| Field | Type | Properties |\n|---|---|---|\n| created_at | DateTimeField | Blank |\n| updated_at | DateTimeField | Blank |\n| id | UUIDField | PK, Unique |\n| tenant | ForeignKey | FK -> Tenant |\n| subscription | ForeignKey | Nullable, FK -> Subscription |\n| invoice_number | CharField | Unique |\n| invoice_date | DateField |  |\n| base_amount | DecimalField |  |\n| cgst_rate | DecimalField |  |\n| sgst_rate | DecimalField |  |\n| igst_rate | DecimalField |  |\n| cgst_amount | DecimalField |  |\n| sgst_amount | DecimalField |  |\n| igst_amount | DecimalField |  |\n| total_amount | DecimalField |  |\n| hsn_sac_code | CharField |  |\n| is_interstate | BooleanField |  |\n| customer_gstin | CharField | Blank |\n| customer_state | CharField | Blank |\n| billing_name | CharField | Blank |\n| billing_address_snapshot | TextField | Blank |\n| payment_status | CharField |  |\n| razorpay_payment_id | CharField | Blank |\n| razorpay_order_id | CharField | Blank |\n| billing_period_start | DateField | Nullable, Blank |\n| billing_period_end | DateField | Nullable, Blank |\n| due_date | DateField | Nullable, Blank |\n| paid_at | DateTimeField | Nullable, Blank |\n| invoice_pdf | FileField | Nullable, Blank |\n\n## Super Admin (apps.superadmin)\n\n### AuditLog\n*Table: superadmin_auditlog*\n> Immutable audit trail for all significant platform actions.
    Never update or delete these records.

    Covers:
    - Super admin actions (tenant CRUD, plan changes)
    - Tenant admin actions (agent CRUD, settings changes)
    - System actions (trial expiry, subscription events)
    - Security events (login, failed login, password reset)\n\n| Field | Type | Properties |\n|---|---|---|\n| id | UUIDField | PK, Unique |\n| actor_type | CharField |  |\n| actor_id | CharField | Blank |\n| actor_email | CharField | Blank |\n| actor_ip | GenericIPAddressField | Nullable, Blank |\n| actor_user_agent | CharField | Blank |\n| tenant_schema | CharField | Blank |\n| action | CharField |  |\n| entity_type | CharField | Blank |\n| entity_id | CharField | Blank |\n| entity_repr | CharField | Blank |\n| changes | JSONField | Blank |\n| description | TextField | Blank |\n| is_sensitive | BooleanField |  |\n| timestamp | DateTimeField |  |\n\n### GlobalSettings\n*Table: superadmin_globalsettings*\n> Platform-wide key-value settings managed by super admins.
    Cached in Redis for fast access.

    Examples:
        key="maintenance_mode",     value="false"
        key="default_trial_days",   value="14"
        key="platform_name",        value="TeleCRM"\n\n| Field | Type | Properties |\n|---|---|---|\n| id | BigAutoField | PK, Unique, Blank |\n| created_at | DateTimeField | Blank |\n| updated_at | DateTimeField | Blank |\n| key | CharField | Unique |\n| value | TextField |  |\n| description | CharField | Blank |\n| updated_by | CharField | Blank |\n\n### SupportNote\n*Table: superadmin_supportnote*\n> Internal notes that super admins write about a tenant.
    Visible only in the super admin panel — NOT to the tenant.\n\n| Field | Type | Properties |\n|---|---|---|\n| id | BigAutoField | PK, Unique, Blank |\n| created_at | DateTimeField | Blank |\n| updated_at | DateTimeField | Blank |\n| tenant | ForeignKey | FK -> Tenant |\n| note | TextField |  |\n| created_by | CharField |  |\n| is_pinned | BooleanField |  |\n\n## Authentication (apps.authentication)\n\n### Agent\n*Table: authentication_agent*\n> The CRM agent/user model.
    Lives in each tenant's PostgreSQL schema — completely isolated.

    Authentication: email + password → JWT tokens
    Authorization: role-based (see AgentRole in constants.py)

    This model does NOT extend PermissionsMixin — we use our own
    role-based permission system instead of Django's group/permission system.\n\n| Field | Type | Properties |\n|---|---|---|\n| login_sessions | Reverse Relation | -> AgentLoginSession |\n| team_memberships | Reverse Relation | -> AgentTeam |\n| assigned_leads | Reverse Relation | -> Lead |\n| territory_leads | Reverse Relation | -> Lead |\n| followups | Reverse Relation | -> FollowUp |\n| lead_notes | Reverse Relation | -> LeadNote |\n| lead_activities | Reverse Relation | -> LeadActivity |\n| import_jobs | Reverse Relation | -> LeadImportJob |\n| default_import_assignments | Reverse Relation | -> LeadImportJob |\n| calls | Reverse Relation | -> CallLog |\n| whatsapp_sent | Reverse Relation | -> WhatsAppMessage |\n| created_campaigns | Reverse Relation | -> BulkCampaign |\n| emaillog | Reverse Relation | -> EmailLog |\n| smslog | Reverse Relation | -> SMSLog |\n| id | BigAutoField | PK, Unique, Blank |\n| password | CharField |  |\n| last_login | DateTimeField | Nullable, Blank |\n| created_at | DateTimeField | Blank |\n| updated_at | DateTimeField | Blank |\n| email | CharField | Unique |\n| name | CharField |  |\n| phone | CharField | Blank |\n| employee_id | CharField | Blank |\n| profile_photo | FileField | Nullable, Blank |\n| role | CharField |  |\n| is_tenant_admin | BooleanField |  |\n| is_active | BooleanField |  |\n| must_change_password | BooleanField |  |\n| timezone | CharField |  |\n| language_preference | CharField |  |\n| shift_start | TimeField | Nullable, Blank |\n| shift_end | TimeField | Nullable, Blank |\n| working_days | JSONField | Blank |\n| fcm_token | TextField | Blank |\n| last_login_ip | GenericIPAddressField | Nullable, Blank |\n| total_login_count | PositiveIntegerField |  |\n| last_active_at | DateTimeField | Nullable, Blank |\n\n### AgentLoginSession\n*Table: authentication_agentloginsession*\n> Tracks individual login sessions for agents.
    Used in the monitoring dashboard to show active sessions.\n\n| Field | Type | Properties |\n|---|---|---|\n| id | BigAutoField | PK, Unique, Blank |\n| created_at | DateTimeField | Blank |\n| updated_at | DateTimeField | Blank |\n| agent | ForeignKey | FK -> Agent |\n| login_time | DateTimeField |  |\n| logout_time | DateTimeField | Nullable, Blank |\n| ip_address | GenericIPAddressField | Nullable, Blank |\n| user_agent | CharField | Blank |\n| device_type | CharField |  |\n| is_active | BooleanField |  |\n| jwt_jti | CharField | Blank |\n\n### Team\n*Table: authentication_team*\n> A team of agents managed by one or more managers.\n\n| Field | Type | Properties |\n|---|---|---|\n| memberships | Reverse Relation | -> AgentTeam |\n| id | BigAutoField | PK, Unique, Blank |\n| created_at | DateTimeField | Blank |\n| updated_at | DateTimeField | Blank |\n| name | CharField | Unique |\n| description | TextField | Blank |\n| is_active | BooleanField |  |\n\n### AgentTeam\n*Table: authentication_agentteam*\n> M2M relationship between Agent and Team, with extra metadata.\n\n| Field | Type | Properties |\n|---|---|---|\n| id | BigAutoField | PK, Unique, Blank |\n| agent | ForeignKey | FK -> Agent |\n| team | ForeignKey | FK -> Team |\n| is_team_lead | BooleanField |  |\n| joined_at | DateTimeField |  |\n\n## Leads (apps.leads)\n\n### Lead\n*Table: leads_lead*\n> A sales prospect / customer inquiry.

    Key design decisions:
    - Phone is the primary identifier (Indian B2C sales — mobile-first)
    - Soft-deleted (is_deleted flag) so history is preserved
    - Assigned to one agent but can be reassigned
    - Pipeline stage tracked via status field
    - Custom fields via LeadCustomFieldValue (EAV pattern, bounded by plan)\n\n| Field | Type | Properties |\n|---|---|---|\n| followups | Reverse Relation | -> FollowUp |\n| notes | Reverse Relation | -> LeadNote |\n| activities | Reverse Relation | -> LeadActivity |\n| custom_field_values | Reverse Relation | -> CustomFieldValue |\n| calls | Reverse Relation | -> CallLog |\n| whatsapp_messages | Reverse Relation | -> WhatsAppMessage |\n| campaign_recipients | Reverse Relation | -> CampaignRecipient |\n| emails | Reverse Relation | -> EmailLog |\n| sms_messages | Reverse Relation | -> SMSLog |\n| id | BigAutoField | PK, Unique, Blank |\n| created_at | DateTimeField | Blank |\n| updated_at | DateTimeField | Blank |\n| is_deleted | BooleanField |  |\n| deleted_at | DateTimeField | Nullable, Blank |\n| deleted_by_id | BigIntegerField | Nullable, Blank |\n| name | CharField |  |\n| phone | CharField |  |\n| alternate_phone | CharField | Blank |\n| email | CharField | Blank |\n| city | CharField | Blank |\n| state | CharField | Blank |\n| pincode | CharField | Blank |\n| address | TextField | Blank |\n| source | CharField |  |\n| status | CharField |  |\n| priority | CharField |  |\n| budget | DecimalField | Nullable, Blank |\n| requirement | TextField | Blank |\n| score | PositiveSmallIntegerField |  |\n| assigned_to | ForeignKey | Nullable, Blank, FK -> Agent |\n| assigned_at | DateTimeField | Nullable, Blank |\n| territory_manager | ForeignKey | Nullable, Blank, FK -> Agent |\n| pipeline_stage | PositiveSmallIntegerField |  |\n| expected_close_date | DateField | Nullable, Blank |\n| deal_value | DecimalField | Nullable, Blank |\n| source_meta | JSONField | Blank |\n| source_lead_id | CharField | Blank |\n| next_followup_at | DateTimeField | Nullable, Blank |\n| last_contacted_at | DateTimeField | Nullable, Blank |\n| contact_count | PositiveIntegerField |  |\n| is_dnd | BooleanField |  |\n| import_job | ForeignKey | Nullable, Blank, FK -> LeadImportJob |\n| tags | JSONField | Blank |\n\n### FollowUp\n*Table: leads_followup*\n> A scheduled follow-up action for a lead.
    Can be a callback, WhatsApp, email, physical visit, etc.\n\n| Field | Type | Properties |\n|---|---|---|\n| id | BigAutoField | PK, Unique, Blank |\n| created_at | DateTimeField | Blank |\n| updated_at | DateTimeField | Blank |\n| lead | ForeignKey | FK -> Lead |\n| assigned_to | ForeignKey | FK -> Agent |\n| followup_type | CharField |  |\n| scheduled_at | DateTimeField |  |\n| notes | TextField | Blank |\n| is_completed | BooleanField |  |\n| completed_at | DateTimeField | Nullable, Blank |\n| completion_notes | TextField | Blank |\n| reminder_sent | BooleanField |  |\n| reminder_sent_at | DateTimeField | Nullable, Blank |\n\n### LeadNote\n*Table: leads_leadnote*\n> A note or comment attached to a lead.
    Records of agent interactions, observations, customer feedback.\n\n| Field | Type | Properties |\n|---|---|---|\n| id | BigAutoField | PK, Unique, Blank |\n| created_at | DateTimeField | Blank |\n| updated_at | DateTimeField | Blank |\n| lead | ForeignKey | FK -> Lead |\n| agent | ForeignKey | Nullable, FK -> Agent |\n| content | TextField |  |\n| is_pinned | BooleanField |  |\n| attachment | FileField | Nullable, Blank |\n\n### LeadActivity\n*Table: leads_leadactivity*\n> Immutable audit trail of everything that happened to a lead.
    Append-only — never update or delete entries.

    Types: call, whatsapp, email, sms, status_change, assigned,
           note_added, followup_created, followup_completed, imported\n\n| Field | Type | Properties |\n|---|---|---|\n| id | BigAutoField | PK, Unique, Blank |\n| lead | ForeignKey | FK -> Lead |\n| activity_type | CharField |  |\n| description | TextField |  |\n| performed_by | ForeignKey | Nullable, Blank, FK -> Agent |\n| meta | JSONField | Blank |\n| timestamp | DateTimeField |  |\n\n### CustomField\n*Table: leads_customfield*\n> Tenant-defined custom field for the Lead model.
    Rendered as extra input in the lead form.
    Limited by plan (max_custom_fields).\n\n| Field | Type | Properties |\n|---|---|---|\n| values | Reverse Relation | -> CustomFieldValue |\n| id | BigAutoField | PK, Unique, Blank |\n| created_at | DateTimeField | Blank |\n| updated_at | DateTimeField | Blank |\n| name | CharField |  |\n| field_key | SlugField | Unique |\n| field_type | CharField |  |\n| is_required | BooleanField |  |\n| is_active | BooleanField |  |\n| sort_order | PositiveSmallIntegerField |  |\n| options | JSONField | Blank |\n| placeholder | CharField | Blank |\n\n### CustomFieldValue\n*Table: leads_customfieldvalue*\n> Stores the value of a CustomField for a specific Lead.
    EAV (Entity-Attribute-Value) pattern — bounded to plan limit.\n\n| Field | Type | Properties |\n|---|---|---|\n| id | BigAutoField | PK, Unique, Blank |\n| lead | ForeignKey | FK -> Lead |\n| field | ForeignKey | FK -> CustomField |\n| value | TextField | Blank |\n\n### LeadImportJob\n*Table: leads_leadimportjob*\n> Tracks a CSV/Excel import operation.
    Stores per-row results so the user can see errors and download a failure report.\n\n| Field | Type | Properties |\n|---|---|---|\n| leads | Reverse Relation | -> Lead |\n| created_at | DateTimeField | Blank |\n| updated_at | DateTimeField | Blank |\n| id | UUIDField | PK, Unique |\n| imported_by | ForeignKey | Nullable, FK -> Agent |\n| file | FileField |  |\n| original_filename | CharField |  |\n| status | CharField |  |\n| column_mapping | JSONField |  |\n| duplicate_action | CharField |  |\n| default_assigned_to | ForeignKey | Nullable, Blank, FK -> Agent |\n| default_source | CharField |  |\n| total_rows | PositiveIntegerField |  |\n| processed_rows | PositiveIntegerField |  |\n| successful_rows | PositiveIntegerField |  |\n| failed_rows | PositiveIntegerField |  |\n| duplicate_rows | PositiveIntegerField |  |\n| row_errors | JSONField | Blank |\n| completed_at | DateTimeField | Nullable, Blank |\n| celery_task_id | CharField | Blank |\n\n## Calls (apps.calls)\n\n### CallDisposition\n*Table: calls_calldisposition*\n> Configurable call outcome options (per tenant).
    Examples: Connected, Not Reachable, Busy, Switched Off, Wrong Number, Callback Requested
    Tenants can add custom dispositions.\n\n| Field | Type | Properties |\n|---|---|---|\n| calls | Reverse Relation | -> CallLog |\n| id | BigAutoField | PK, Unique, Blank |\n| created_at | DateTimeField | Blank |\n| updated_at | DateTimeField | Blank |\n| name | CharField |  |\n| slug | SlugField | Unique |\n| is_positive | BooleanField |  |\n| is_active | BooleanField |  |\n| sort_order | PositiveSmallIntegerField |  |\n| auto_followup_hours | PositiveIntegerField | Nullable, Blank |\n\n### CallLog\n*Table: calls_calllog*\n> A record of a single call (outbound or inbound).
    Created automatically when a call is initiated via click-to-call,
    or manually when agent logs a call they made outside the CRM.\n\n| Field | Type | Properties |\n|---|---|---|\n| recording | Reverse Relation | -> CallRecording |\n| created_at | DateTimeField | Blank |\n| updated_at | DateTimeField | Blank |\n| id | UUIDField | PK, Unique |\n| agent | ForeignKey | Nullable, FK -> Agent |\n| lead | ForeignKey | Nullable, Blank, FK -> Lead |\n| direction | CharField |  |\n| phone_number | CharField |  |\n| started_at | DateTimeField |  |\n| connected_at | DateTimeField | Nullable, Blank |\n| ended_at | DateTimeField | Nullable, Blank |\n| duration_seconds | PositiveIntegerField |  |\n| is_connected | BooleanField |  |\n| disposition | ForeignKey | Nullable, Blank, FK -> CallDisposition |\n| notes | TextField | Blank |\n| provider | CharField | Blank |\n| provider_call_id | CharField | Blank |\n| provider_meta | JSONField | Blank |\n| call_cost_paise | PositiveIntegerField |  |\n\n### CallRecording\n*Table: calls_callrecording*\n> Audio recording metadata for a call.
    The actual file is stored in S3 via PrivateMediaStorage.
    URL generated as a presigned S3 URL (valid 1 hour).\n\n| Field | Type | Properties |\n|---|---|---|\n| id | BigAutoField | PK, Unique, Blank |\n| call | OneToOneField | Unique, FK -> CallLog |\n| file | FileField |  |\n| file_size_bytes | PositiveIntegerField |  |\n| duration_seconds | PositiveIntegerField |  |\n| format | CharField |  |\n| transcript | TextField | Blank |\n| transcript_status | CharField |  |\n| uploaded_at | DateTimeField |  |\n\n## Communications (apps.communications)\n\n### WhatsAppTemplate\n*Table: communications_whatsapptemplate*\n> Pre-approved WhatsApp message template.
    Must be approved by Meta before use in bulk messaging.\n\n| Field | Type | Properties |\n|---|---|---|\n| whatsappmessage | Reverse Relation | -> WhatsAppMessage |\n| campaigns | Reverse Relation | -> BulkCampaign |\n| id | BigAutoField | PK, Unique, Blank |\n| created_at | DateTimeField | Blank |\n| updated_at | DateTimeField | Blank |\n| name | CharField | Unique |\n| category | CharField |  |\n| language | CharField |  |\n| header_text | CharField | Blank |\n| body_text | TextField |  |\n| footer_text | CharField | Blank |\n| variable_mapping | JSONField | Blank |\n| provider | CharField |  |\n| provider_template_id | CharField | Blank |\n| status | CharField |  |\n| is_active | BooleanField |  |\n| usage_count | PositiveIntegerField |  |\n\n### WhatsAppMessage\n*Table: communications_whatsappmessage*\n> A single WhatsApp message sent to or received from a lead.
    Maintains conversation thread per lead.\n\n| Field | Type | Properties |\n|---|---|---|\n| created_at | DateTimeField | Blank |\n| updated_at | DateTimeField | Blank |\n| id | UUIDField | PK, Unique |\n| lead | ForeignKey | FK -> Lead |\n| sent_by | ForeignKey | Nullable, Blank, FK -> Agent |\n| direction | CharField |  |\n| message_type | CharField |  |\n| content | TextField | Blank |\n| template | ForeignKey | Nullable, Blank, FK -> WhatsAppTemplate |\n| provider | CharField |  |\n| provider_message_id | CharField | Blank |\n| status | CharField |  |\n| sent_at | DateTimeField | Nullable, Blank |\n| delivered_at | DateTimeField | Nullable, Blank |\n| read_at | DateTimeField | Nullable, Blank |\n| error_message | CharField | Blank |\n| media_url | CharField | Blank |\n| campaign | ForeignKey | Nullable, Blank, FK -> BulkCampaign |\n\n### BulkCampaign\n*Table: communications_bulkcampaign*\n> A bulk communication campaign targeting multiple leads.
    Supports WhatsApp, Email, and SMS channels.\n\n| Field | Type | Properties |\n|---|---|---|\n| whatsapp_messages | Reverse Relation | -> WhatsAppMessage |\n| recipients | Reverse Relation | -> CampaignRecipient |\n| emails | Reverse Relation | -> EmailLog |\n| sms_messages | Reverse Relation | -> SMSLog |\n| created_at | DateTimeField | Blank |\n| updated_at | DateTimeField | Blank |\n| id | UUIDField | PK, Unique |\n| name | CharField |  |\n| channel | CharField |  |\n| created_by | ForeignKey | Nullable, FK -> Agent |\n| audience_filters | JSONField |  |\n| estimated_recipients | PositiveIntegerField |  |\n| template | ForeignKey | Nullable, Blank, FK -> WhatsAppTemplate |\n| email_subject | CharField | Blank |\n| email_body | TextField | Blank |\n| sms_text | CharField | Blank |\n| sms_sender_id | CharField | Blank |\n| status | CharField |  |\n| scheduled_at | DateTimeField | Nullable, Blank |\n| started_at | DateTimeField | Nullable, Blank |\n| completed_at | DateTimeField | Nullable, Blank |\n| total_recipients | PositiveIntegerField |  |\n| sent_count | PositiveIntegerField |  |\n| delivered_count | PositiveIntegerField |  |\n| failed_count | PositiveIntegerField |  |\n| replied_count | PositiveIntegerField |  |\n| celery_task_id | CharField | Blank |\n\n### CampaignRecipient\n*Table: communications_campaignrecipient*\n> Per-lead row in a bulk campaign — tracks individual delivery status.\n\n| Field | Type | Properties |\n|---|---|---|\n| id | BigAutoField | PK, Unique, Blank |\n| campaign | ForeignKey | FK -> BulkCampaign |\n| lead | ForeignKey | FK -> Lead |\n| phone | CharField |  |\n| status | CharField |  |\n| error_message | CharField | Blank |\n| sent_at | DateTimeField | Nullable, Blank |\n| provider_message_id | CharField | Blank |\n\n### EmailLog\n*Table: communications_emaillog*\n> Record of a single email sent from the CRM.\n\n| Field | Type | Properties |\n|---|---|---|\n| created_at | DateTimeField | Blank |\n| updated_at | DateTimeField | Blank |\n| id | UUIDField | PK, Unique |\n| lead | ForeignKey | Nullable, Blank, FK -> Lead |\n| sent_by | ForeignKey | Nullable, Blank, FK -> Agent |\n| campaign | ForeignKey | Nullable, Blank, FK -> BulkCampaign |\n| to_email | CharField |  |\n| subject | CharField |  |\n| body | TextField |  |\n| status | CharField |  |\n| provider | CharField | Blank |\n| provider_message_id | CharField | Blank |\n| sent_at | DateTimeField | Nullable, Blank |\n| opened_at | DateTimeField | Nullable, Blank |\n| error_message | CharField | Blank |\n\n### SMSLog\n*Table: communications_smslog*\n> Record of a single SMS sent from the CRM.\n\n| Field | Type | Properties |\n|---|---|---|\n| created_at | DateTimeField | Blank |\n| updated_at | DateTimeField | Blank |\n| id | UUIDField | PK, Unique |\n| lead | ForeignKey | Nullable, Blank, FK -> Lead |\n| sent_by | ForeignKey | Nullable, Blank, FK -> Agent |\n| campaign | ForeignKey | Nullable, Blank, FK -> BulkCampaign |\n| phone_number | CharField |  |\n| message | CharField |  |\n| sender_id | CharField | Blank |\n| status | CharField |  |\n| provider | CharField | Blank |\n| provider_message_id | CharField | Blank |\n| sent_at | DateTimeField | Nullable, Blank |\n| delivered_at | DateTimeField | Nullable, Blank |\n| error_message | CharField | Blank |\n| cost_paise | PositiveIntegerField |  |\n\n## Integrations (apps.integrations)\n\n### LeadSourceConfig\n*Table: integrations_leadsourceconfig*\n> Per-tenant configuration for a lead source integration.
    Stores provider-specific credentials and options.\n\n| Field | Type | Properties |\n|---|---|---|\n| webhook_logs | Reverse Relation | -> WebhookLog |\n| id | BigAutoField | PK, Unique, Blank |\n| created_at | DateTimeField | Blank |\n| updated_at | DateTimeField | Blank |\n| source | CharField | Unique |\n| is_active | BooleanField |  |\n| status | CharField |  |\n| credentials | JSONField | Blank |\n| options | JSONField | Blank |\n| webhook_token | CharField | Blank |\n| total_leads_received | PositiveIntegerField |  |\n| last_received_at | DateTimeField | Nullable, Blank |\n| error_message | CharField | Blank |\n\n### WebhookLog\n*Table: integrations_webhooklog*\n> Log of every inbound webhook payload for debugging and replay.\n\n| Field | Type | Properties |\n|---|---|---|\n| created_at | DateTimeField | Blank |\n| updated_at | DateTimeField | Blank |\n| id | UUIDField | PK, Unique |\n| source | CharField |  |\n| config | ForeignKey | Nullable, FK -> LeadSourceConfig |\n| method | CharField |  |\n| headers | JSONField | Blank |\n| payload | JSONField | Blank |\n| processed | BooleanField |  |\n| leads_created | PositiveSmallIntegerField |  |\n| leads_updated | PositiveSmallIntegerField |  |\n| error | CharField | Blank |\n
---

## Recruitment / ATS (apps.recruitment)

Tenant-schema models for the Recruitment add-on module (`ModuleKey.RECRUITMENT`).

### JobOpening
*Table: recruitment_jobopening*
> A role being hired for. `openings` is how many people; `hired_count` counts
> applications that reached HIRED, so `is_filled` is derived, never stored.

| Field | Type | Notes |
|---|---|---|
| title | CharField | |
| code | CharField | Unique, indexed |
| department / location | CharField | Blank |
| employment_type | CharField | Shares `hrms.EmploymentType` |
| openings | PositiveIntegerField | Positions to fill |
| min/max_experience_years | DecimalField | max nullable |
| salary_min / salary_max | DecimalField | Nullable. Commercially sensitive — gated behind `ats.view` |
| description | TextField | JD |
| hiring_manager | FK → authentication.Agent | Nullable |
| status | CharField | draft / open / on_hold / closed |
| opened_on / closed_on | DateField | Nullable |

### PipelineStage
*Table: recruitment_pipelinestage*
> Configurable per tenant, because every company names its stages differently.
> `is_terminal` marks a stage nobody moves out of. Seeded lazily with six
> defaults on first read (`services/pipeline.seed_pipeline`).

| Field | Type | Notes |
|---|---|---|
| name | CharField | Unique |
| order | PositiveIntegerField | Indexed; rewritten by the reorder endpoint |
| is_terminal | BooleanField | Hired / Rejected |
| is_active | BooleanField | Deactivated rather than deleted (applications PROTECT it) |

### Candidate
*Table: recruitment_candidate*
> A PERSON, stored once, independent of the roles they apply for. That is what
> makes "have we seen this person before?" answerable.

| Field | Type | Notes |
|---|---|---|
| name / email / phone | CharField | All indexed; email+phone composite index for dedupe |
| source | CharField | referral / job_board / linkedin / careers_page / agency / walk_in / other |
| referred_by | FK → Agent | Nullable |
| current_company / current_designation | CharField | Blank |
| total_experience_years | DecimalField | |
| current_ctc / expected_ctc | DecimalField | Nullable |
| notice_period_days | PositiveIntegerField | |
| skills | JSONField | List of strings |
| resume | FileField | `recruitment/resumes/` |
| is_active | BooleanField | Archive flag — never hard-deleted |

### Application
*Table: recruitment_application*
> One candidate against one opening. **Unique on (candidate, opening)** — a
> double-click on "Apply" must not create a second pipeline entry.

| Field | Type | Notes |
|---|---|---|
| candidate | FK → Candidate | CASCADE |
| opening | FK → JobOpening | CASCADE |
| stage | FK → PipelineStage | PROTECT |
| status | CharField | active / hired / rejected / withdrawn / on_hold — a hard enum, so reporting never depends on stage naming |
| owner | FK → Agent | The recruiter driving it |
| applied_on | DateField | |
| rating | PositiveSmallIntegerField | Nullable, recruiter's own 1–5 |
| stage_changed_at | DateTimeField | Drives `days_in_stage` |

### ApplicationActivity
*Table: recruitment_applicationactivity*
> Append-only audit trail. Never updated or deleted — "who moved this candidate
> to Rejected, and when?" gets asked months later.

| Field | Type | Notes |
|---|---|---|
| application | FK → Application | CASCADE |
| kind | CharField | created / stage_change / status_change / note / interview / feedback / offer |
| summary / detail | CharField / TextField | |
| actor | FK → Agent | Nullable (system actions) |

### Interview
*Table: recruitment_interview*

| Field | Type | Notes |
|---|---|---|
| application | FK → Application | CASCADE |
| round_number | PositiveSmallIntegerField | |
| scheduled_at | DateTimeField | Indexed with status |
| duration_minutes | PositiveSmallIntegerField | |
| mode | CharField | phone / video / onsite |
| interviewers | M2M → Agent | The panel |
| status | CharField | scheduled / completed / cancelled / no_show |

### InterviewFeedback
*Table: recruitment_interviewfeedback*
> **One row per interviewer**, unique on (interview, interviewer). A panel where
> three people disagree is the interesting case; one shared row would lose it.

| Field | Type | Notes |
|---|---|---|
| interview | FK → Interview | CASCADE |
| interviewer | FK → Agent | CASCADE |
| recommendation | CharField | strong_no … strong_yes (weighted 1–5 for averaging) |
| scores | JSONField | Per-criterion scores |
| strengths / concerns / comments | TextField | |

### Offer
*Table: recruitment_offer*
> One-to-one with Application. `converted_employee` is what makes the HRMS
> handover idempotent — a second click returns the same employee.

| Field | Type | Notes |
|---|---|---|
| application | OneToOneField → Application | CASCADE |
| annual_ctc | DecimalField | |
| fixed_component / variable_component / joining_bonus | DecimalField | Fixed seeds the HRMS salary structure |
| designation / department / employment_type | CharField | Copied to the Employee on conversion |
| reporting_to | FK → hrms.Employee | Nullable |
| joining_date / valid_until | DateField | |
| offer_letter | FileField | `recruitment/offers/` |
| status | CharField | draft → sent → accepted / declined / revoked |
| converted_employee | FK → hrms.Employee | Nullable; set once onboarded |

---

## Roles & capabilities (apps.core)

`AgentRole` gained two back-office roles that sit deliberately outside the CRM
hierarchy, so a person can own a business module without being handed the CRM:

| Role | Owns | Deliberately cannot |
|---|---|---|
| `hr` | HRMS end-to-end incl. payroll, Recruitment | Tenant settings, agent management, billing |
| `accounts` | Sales & Billing incl. issuing/cancelling invoices | Payroll, tenant settings, agent management |

Module access is decided by `apps/core/capabilities.py` (a role list per action),
**not** by `AgentRole.HIERARCHY`. Endpoints declare `required_capability` and are
guarded by `HasCapability` alongside the existing `HasFeatureAccess` plan gate.
The same table is served to clients at `GET /api/v1/auth/capabilities/`.

---

## Lead batches (apps.leads)

### LeadBatch
*Table: leads_leadbatch*
> A named consignment of leads that arrived together — the unit admins
> distribute by. Two things create one: a CSV/Excel import (one batch per job),
> or a webhook/API source (one batch per SOURCE PER DAY, opened on first
> arrival and reused for the rest of that day).
>
> Per-day for webhooks because leads trickle in one at a time: a batch per lead
> is meaningless, and one rolling batch grows unbounded until somebody
> remembers to close it. A day is the unit people already think in when they
> look at ad spend.

| Field | Type | Notes |
|---|---|---|
| number | PositiveIntegerField | Unique, nullable. Seeded from the row's own **pk**, so it is monotonic and **never reused after a delete** — `max(number)+1` would hand a deleted batch's number to the next one, and an admin's note saying "distribute batch 2" would then point at a different consignment. Null only between INSERT and that update. |
| name | CharField | Admin's label. Blank → see `label`. |
| label | *property* | `name` if set; else source + date for webhook batches; else "Batch &lt;n&gt;". |
| kind | CharField | import / webhook / manual |
| source | CharField | LeadSource — indexed with collection_date |
| status | CharField | open / closed |
| collection_date | DateField | The day a webhook batch collects. Null for imports. |
| import_job | OneToOne → LeadImportJob | Null for webhook batches |
| total_leads | PositiveIntegerField | Denormalised; `recount()` repairs drift |

**Constraint** `uniq_webhook_batch_per_source_day` — a partial unique index on
(source, collection_date) where kind='webhook'. This is what makes
`open_for_source` safe when two webhook deliveries land in the same
millisecond, which for an active ad campaign is routine.

`Lead.batch` is a nullable FK with its own index — the filter behind every
distribute-by-batch action.

### LeadImportJob — batch & auto-assign fields

| Field | Type | Notes |
|---|---|---|
| batch_name | CharField | Admin's label, chosen at upload time |
| auto_assign | BooleanField | Distribute when the import finishes |
| assign_method | CharField | round_robin / equal_split / least_loaded |
| assign_to_agents | JSONField | Agent ids; **order is respected** by round robin |
| assign_max_per_agent | PositiveIntegerField | Ceiling on an agent's TOTAL open leads. Null = no cap. |
| assignment_result | JSONField | What the distribution actually did, for the UI |

---

## Distribution engine (apps/leads/services/distribution.py)

One module shared by the import task's auto-assign, the manual Distribute
action and the batch-scoped distribute. The round-robin used to live inline in
`LeadDistributeView`, which is precisely why the import path could not reuse it.

| Method | Behaviour |
|---|---|
| `round_robin` | One at a time in agent order. Skips a capped agent rather than stalling the rotation. |
| `equal_split` | Contiguous blocks — useful when the file is ordered by something the admin cares about. |
| `least_loaded` | Fewest open leads first, re-evaluated per lead so one agent doesn't take everything. |

`plan()` is pure — same inputs, same split — so a preview cannot disagree with
what actually happens. It returns leftovers rather than force-assigning them:
when every agent is at the cap, those leads stay unassigned and visible, and
the API says how many.

"Open" excludes converted, lost, duplicate **and not_interested**: counting
finished work would mean the agent who closes the most deals stops receiving
any new ones.
