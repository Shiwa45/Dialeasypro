"""
TeleCRM Backend — apps/tenants/throttles.py

Limits on creating a tenant. Every signup builds a whole PostgreSQL schema
and runs every tenant migration into it, and there is no email-verification
step, so signups were cheap to abuse at the old 10/hour per IP (MED-10).

Three layers, all on DRF's cache-backed throttle:
  registration          — per IP, short burst   (settings: 3/hour)
  registration_daily    — per IP, per day       (settings: 10/day)
  registration_platform — everyone together     (settings: 200/day), so a
                          spread of addresses cannot run the database dry.
"""
from rest_framework.throttling import SimpleRateThrottle


class RegistrationBurstThrottle(SimpleRateThrottle):
    scope = "registration"

    def get_cache_key(self, request, view):
        return self.cache_format % {"scope": self.scope, "ident": self.get_ident(request)}


class RegistrationDailyThrottle(RegistrationBurstThrottle):
    scope = "registration_daily"


class RegistrationPlatformThrottle(SimpleRateThrottle):
    scope = "registration_platform"

    def get_cache_key(self, request, view):
        return self.cache_format % {"scope": self.scope, "ident": "all"}
