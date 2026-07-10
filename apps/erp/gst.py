"""
TeleCRM Backend — apps/erp/gst.py

GST computation for TENANT → CUSTOMER invoices.

This is deliberately NOT apps.core.constants.GSTState.get_gst_components: that
helper is hardcoded to TeleCRM's own registered state and a flat 18% SaaS rate,
because it bills *our* subscribers. Here the seller is the tenant (their state,
their GSTIN) and the rate comes from each product's HSN/SAC classification.

Rules implemented
-----------------
* Intra-state supply (seller state == buyer state) → CGST + SGST, each rate/2.
* Inter-state supply                                → IGST at the full rate.
* Tax is computed per line, on the post-discount taxable value, and rounded to
  2 dp per line (matching how Indian accounting packages and Tally do it).
  Summing pre-rounded line taxes and rounding once at the end produces figures
  that disagree with the customer's own books by a paisa or two.
* The invoice total is rounded to the nearest rupee, and the difference is
  carried in an explicit `round_off` field — an invoice must foot exactly.

Union territories charge UTGST rather than SGST. The split is identical
(rate/2), so UT supply is handled as intra-state and the SGST column carries
the UTGST amount; the invoice template should label it accordingly.
"""
from decimal import ROUND_HALF_UP, Decimal

PAISA = Decimal("0.01")
RUPEE = Decimal("1")

# Valid GST slabs in India. Anything else is a data-entry error.
VALID_GST_RATES = [Decimal("0"), Decimal("5"), Decimal("12"), Decimal("18"), Decimal("28")]


def q2(value: Decimal) -> Decimal:
    """Round to 2 decimal places, half-up (the convention Indian tax uses)."""
    return Decimal(value).quantize(PAISA, rounding=ROUND_HALF_UP)


def line_taxable_value(quantity: Decimal, unit_price: Decimal, discount_percent: Decimal) -> Decimal:
    """Post-discount value of a line, before tax."""
    gross = Decimal(quantity) * Decimal(unit_price)
    discount = gross * Decimal(discount_percent) / Decimal("100")
    return q2(gross - discount)


def split_gst(
    taxable_value: Decimal,
    gst_rate: Decimal,
    *,
    seller_state: str,
    buyer_state: str,
) -> dict:
    """
    Split a line's tax into CGST/SGST or IGST.

    Returns rates and amounts. When either state code is missing we cannot know
    the place of supply, so we fall back to intra-state (CGST+SGST) — the
    conservative choice for a domestic seller, and visible on the invoice.
    """
    rate = Decimal(gst_rate)
    taxable = q2(taxable_value)

    interstate = bool(seller_state and buyer_state) and (
        seller_state.strip().upper() != buyer_state.strip().upper()
    )

    if interstate:
        igst = q2(taxable * rate / Decimal("100"))
        return {
            "is_interstate": True,
            "cgst_rate": Decimal("0"), "sgst_rate": Decimal("0"), "igst_rate": rate,
            "cgst_amount": Decimal("0.00"), "sgst_amount": Decimal("0.00"), "igst_amount": igst,
            "tax_amount": igst,
        }

    half = rate / Decimal("2")
    cgst = q2(taxable * half / Decimal("100"))
    # Derive SGST from the total rather than recomputing, so cgst+sgst always
    # equals the full tax even when rate/2 doesn't divide cleanly (e.g. 5%).
    total_tax = q2(taxable * rate / Decimal("100"))
    sgst = q2(total_tax - cgst)

    return {
        "is_interstate": False,
        "cgst_rate": half, "sgst_rate": half, "igst_rate": Decimal("0"),
        "cgst_amount": cgst, "sgst_amount": sgst, "igst_amount": Decimal("0.00"),
        "tax_amount": q2(cgst + sgst),
    }


def round_off(total: Decimal) -> tuple[Decimal, Decimal]:
    """
    (rounded_total, round_off_delta) — invoices are settled to whole rupees.
    delta = rounded - exact, so exact + delta == rounded, and the invoice foots.
    """
    exact = q2(total)
    rounded = exact.quantize(RUPEE, rounding=ROUND_HALF_UP)
    return rounded, q2(rounded - exact)


def summarize(lines: list[dict]) -> dict:
    """
    Roll up per-line tax dicts (each already split) into document totals.

    `lines` items must carry: taxable_value, cgst_amount, sgst_amount,
    igst_amount. Returns document totals plus the whole-rupee rounding.
    """
    subtotal = sum((Decimal(l["taxable_value"]) for l in lines), Decimal("0"))
    cgst = sum((Decimal(l["cgst_amount"]) for l in lines), Decimal("0"))
    sgst = sum((Decimal(l["sgst_amount"]) for l in lines), Decimal("0"))
    igst = sum((Decimal(l["igst_amount"]) for l in lines), Decimal("0"))

    total_tax = q2(cgst + sgst + igst)
    grand_exact = q2(q2(subtotal) + total_tax)
    grand, delta = round_off(grand_exact)

    return {
        "subtotal": q2(subtotal),
        "cgst_amount": q2(cgst),
        "sgst_amount": q2(sgst),
        "igst_amount": q2(igst),
        "total_tax": total_tax,
        "round_off": delta,
        "total_amount": grand,
    }
