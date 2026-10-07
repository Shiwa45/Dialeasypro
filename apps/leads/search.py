"""
TeleCRM Backend — apps/leads/search.py

One meaning of "search leads" for the list, the export and bulk assignment.

It used to be `name OR phone OR email icontains <term>`, which missed:
  * phone numbers typed the way people write them — "99302 15251",
    "099302 15251", "+91 99302-15251" (the stored form is +919930215251);
  * names typed in another order — "mishra rohan" for "Rohan Mishra";
  * the source, which the top search box promises ("Search leads, phone,
    name, source…") — "Meta" or "IndiaMART" found nothing.
"""
import re

from django.db.models import Q

from apps.core.constants import LeadSource


def lead_search_q(term: str) -> Q:
    term = (term or "").strip()
    if not term:
        return Q()

    words = term.split()
    q = Q(email__icontains=term) | Q(phone__icontains=term)

    # Every word somewhere in the name, in any order.
    name_q = Q()
    for word in words:
        name_q &= Q(name__icontains=word)
    q |= name_q

    digits = re.sub(r"\D", "", term)
    if len(digits) >= 4 and len(digits) >= len(re.sub(r"\s", "", term)) - 3:
        # Mostly digits → a phone number. Compare on the national number:
        # drop a trunk 0 or the 91 country code, keep the last 10 digits.
        if len(digits) == 11 and digits.startswith("0"):
            digits = digits[1:]
        elif len(digits) == 12 and digits.startswith("91"):
            digits = digits[2:]
        q |= Q(phone__icontains=digits) | Q(alternate_phone__icontains=digits)

    lowered = term.lower()
    sources = [
        value for value, label in LeadSource.CHOICES
        if lowered in label.lower() or lowered == value
    ]
    if sources:
        q |= Q(source__in=sources)
    return q
