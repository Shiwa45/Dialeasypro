# Sales & Billing — QA report (live site)

**Tested:** easyian.shop, workspace `crm`, signed in as admin · 7 Oct 2026 · after the round-1 fixes were deployed
**Seller set-up during the test:** company "crm", state UP, **no GSTIN**.
**What was done (all real records, prefixed "QA Test"):**

- Customers: 4 added (B2B MH, B2C UP, B2B KA, GSTIN with no state), 1 duplicate added then deleted. Edited one, tried bad email, short GSTIN, mismatched GSTIN.
- Products: 6 added (goods with stock, service, 0 %, 5 %, 12 %, 18 %). Edited one, adjusted stock, deleted one. Tried duplicate SKU, negative price, bad unit, bad HSN.
- Quotations: 4 created, with lines, discounts, decimal quantity, line removal, sent, accepted, rejected. QUO/…/00002 was converted to an order.
- Orders: 2 created, each with an invoice raised.
- Invoices: 1 edited, issued, part-paid (UPI), then fully paid (cheque). 1 issued, then cancelled with a reason. 1 draft deleted.
- Also checked: payments list, customer history, GST summary, dashboard and filters.

All GST maths checked by hand. Line totals, CGST/SGST vs IGST, round-off and amount-in-words were **correct** whenever the buyer's state was known.

Severity: 🔴 blocks the flow or produces a wrong tax document · 🟠 wrong data / broken feature · 🟡 polish

---

## 🔴 Blockers and wrong tax documents

| # | Where | Problem | Cause (verified) |
|---|---|---|---|
| E11 | Quotations → New quotation | **Every new quotation fails** with "Could not create the quotation" (server error 500). | `QuotationListCreateView.create` passes `quotation_date=None` when the form doesn't send a date (it never does), and the column is NOT NULL. Reproduced in a test. I created the test quotations by sending a date directly to the API. |
| E12 | Invoices → New invoice | **A stand-alone invoice can never be created.** The screen POSTs to `/erp/invoices/`, but that endpoint is list-only (405). | `InvoiceListView` is a `ListAPIView`. `services.create_invoice()` exists but no view calls it. |
| E37 | Exports → Tally / Zoho CSV | **The export download breaks** as soon as there is any issued invoice. The response is cut off mid-stream. | `TallyExportView` calls `qs.iterator()` after `prefetch_related()` without `chunk_size`, which Django 5 rejects (`ValueError`). Reproduced. |
| E4 | Customers → GST | A customer with a GSTIN but **no state** is accepted, and the state is not read from the GSTIN. QUO 00004 / INV 00002 for a Delhi GSTIN (07…) were taxed **CGST + SGST** instead of **IGST** (seller UP). | No state derivation; an empty buyer state falls back to intra-state. |
| E1 | Customers | GSTIN state code isn't checked against the chosen state (09 = UP accepted with state MH). Format and checksum aren't validated either, only length. The form tells users they must match. | Serializer only checks length. |
| E28 | Invoices → Issue | A **TAX INVOICE was issued with no supplier GSTIN**: the company profile has none. A GST tax invoice must carry it. | No check on issue. |
| E26 | Invoice line editor | Any GST rate is accepted on a line; **7 %** was saved. Products are limited to 0/5/12/18/28, lines are not. | No rate validation on line serializers. |
| E29 | Stock | **Stock never goes down.** Issuing an invoice for 2 × a stock-tracked laptop left stock at 12. | Nothing in the code decrements `stock_quantity`. |
| E36 | Invoices filter + Customer → History | The **customer filter is ignored**. Customer History shows other customers' invoices: QA Test Retail, which has no invoices, shows "₹1,72,394 billed, 2 invoices". | `InvoiceListView.get_queryset` handles status/date but not `customer`. |
| E38 | Customer → History | "Outstanding" counts a **cancelled** invoice (₹53,100 shown as outstanding). | — |

## 🟠 Broken or wrong behaviour

| # | Where | Problem |
|---|---|---|
| E2 | All Sales & Billing forms | Errors show **"Failed — validation_error Validation failed. [object Object]"**. The real message (bad email, duplicate SKU, bad unit, discount over 100) is never shown, and no field is highlighted. On line items it's just "Could not add the line item." (E18). |
| E17 | Quotation & invoice lines | **Manual / custom lines can't be saved** ("product: This field may not be null"), although both forms offer "fill in manually" / "Custom line (no product)". Freight, packing, one-off service charges are impossible. |
| E16 | Quotation document (and builder) | Money is shown in short form on the **printable quotation**: rate "₹45.0K", taxable "₹81.0K", IGST "₹14.6K", total "₹95.6K", round-off "₹0" (was ₹0.40), CGST "₹518" (was ₹517.50). The invoice document correctly uses exact rupees. |
| E8 | Products → Unit | Unit is a free-text box, but the server accepts only nos/hour/day/month/kg/litre/meter. "job", "ream", "box", "pcs" fail (with the [object Object] error). Needs a dropdown, and probably pcs/box/set/pack/sqft. |
| E10 / E15 | Product edit, quotation line | The GST dropdown **shows 0 %** for every product: the server sends "18.00" and the options are "18". The saved rate is unchanged unless the user touches the dropdown, which makes it easy to save a 0 % they didn't mean. |
| E25 | Invoice numbering | An invoice raised from an order takes its GST number as a **draft** (INV/…/00003). Deleting it leaves a **gap** in the GST series, while the delete dialog says "Drafts have no GST number yet, so deleting one leaves no hole". The next invoice will be 00004. |
| E39 | Invoices / quotations | No way to set a **due date** on an invoice raised from an order, and none to edit notes / due date / valid-until after creation (`updateInvoice`/`updateQuotation` exist but no screen uses them). Overdue and ageing can never work for these invoices. |
| E40 | Delete customer / product in use | The server returns a **500 error** instead of the friendly "it's used on documents" message. |
| E27 | Issue invoice | Issues **immediately with no confirmation**, though it's irreversible. |
| E20 | Quotation after "sent" | Lines can still be **added or removed** after the quotation is marked sent, so the system no longer matches what the customer received. |
| E19 / E21 | Quotation status | An **empty** (₹0) quotation that has **already expired** can be marked sent and accepted. |
| E13 | New quotation | "Valid until" can be **before** the quotation date (an already-expired quote). |
| E31 | Payments | A payment dated in the **future** (15 Jan 2027) is accepted. |
| E33 | Payments | A wrongly recorded payment can't be **deleted or reversed** anywhere. |
| E32 | Cancel paid invoice | The refusal says "refund and issue a credit note", but there is **no credit-note feature**. |
| E22 | Sales Orders filter | Offers Confirmed / Invoiced / Cancelled, but new orders are **OPEN**: no Open option, and "Confirmed" finds nothing. |
| E24 | Sales Orders | No way to **cancel** an order from the screen. |
| E35 | Sales Orders | After its invoice is cancelled, the order still shows **INVOICED** (a new invoice can still be raised). |
| E7 | Customers | Can't mark a customer **inactive**: the delete dialog suggests it, but the edit form has no Active switch. |
| E14 | Quotation header | An out-of-state quotation with no lines says **"Intra-state (CGST + SGST)"** until the first line is added. |
| E9 | Products | HSN/SAC isn't validated ("ABCD" accepted). |
| E3 | Customers | Phone stored exactly as typed ("98765 43210"), not normalised like leads. |
| E5 | Customers | Duplicate customer names (and GSTINs) are created with no warning. |

## 🟡 Polish

- E6: the Customers list has no search box.
- E23: the order detail hides the discount column, so "2 × ₹45,000 at 18 % = ₹95,580" doesn't add up on screen.
- E30: round-off is printed "₹-0.40" rather than "−₹0.40".
- E34: a **draft** quotation can be converted straight to an order (skipping sent/accepted), while "Customer accepted" is refused for a draft. The two rules disagree.
- The company name prints as **"crm"** on every quotation, invoice and payslip. Set the real name in the company profile.
- The GSTIN input is squeezed to a few characters at medium width in the customer form.

## Worked correctly

- **GST maths:** line taxable value with discount, IGST for MH/KA buyers from UP, CGST+SGST for a UP buyer, 0 % and 5 % / 12 % lines, round-off to the rupee, amount in words. Both totals tested matched to the paisa: ₹1,17,934 / ₹9,385 on the quotations, ₹1,19,294 on the invoice.
- **Number series:** QUO, SO and INV numbers ran in sequence.
- **Quotation steps:** draft → sent → accepted → order. Rejected quotations can't be converted, and a second conversion is refused. A quotation with no lines can't be converted.
- **Order → invoice:** one active invoice per order, re-raisable after cancellation.
- **Invoice:** issue; partial then full payment, with status moving issued → partially paid → paid; overpayment and zero amount blocked; a paid invoice can't be cancelled; cancellation needs a reason and keeps the number.
- **Elsewhere:**
  - The payments list and its filters work.
  - The GST summary (B2B by rate) is correct.
  - The dashboard figures match.
  - Stock can be adjusted by hand.
  - Product and customer edits save.
  - The new-invoice customer picker now lists customers (round-1 fix confirmed).

## Not tested

- **Print / Save as PDF:** opens the browser's print dialog, which the test browser can't drive.
- **The Tally CSV file itself:** the download is broken (E37).

## Test data left in the workspace

Everything is named "QA Test…" or "QA…":

- 4 customers
- 6 products
- 4 quotations (QUO 00001–00004)
- 2 orders (SO 00001–00002)
- Invoices INV 00001 (paid) and 00002 (cancelled)
- 3 payments, including a ₹100 cash payment dated 15 Jan 2027

Issued invoices can only be cancelled, never deleted, so INV 00001–00002 stay in the series. Use a fresh workspace for real billing if that matters.

---

## Fix status (8 Oct 2026)

**Every item above is fixed** (backend + screens). Backend: 744 tests pass, including 23 new regression tests in `apps/erp/tests/test_qa_erp_fixes.py`; frontend type-checks clean.

| Item | Fix |
|---|---|
| E11 | New quotation defaults the date to today; the form also has a date field. |
| E12 | `POST /erp/invoices/` creates a draft invoice. |
| E37 | Tally/Zoho export streams with `iterator(chunk_size=200)`. |
| E1, E4 | GSTIN format, checksum and state code are validated (`apps/erp/gstin.py`). The state is filled in from the GSTIN, and a mismatch is refused. The form fills the state as you type. |
| E28 | A tax invoice can't be issued until the company GSTIN is set. The new **Settings → Company Profile** tab (admins) edits name, GSTIN, state, address and PIN. |
| E26, E10/E15 | Lines accept only 0/5/12/18/28 %. Every GST field is now a dropdown, with "18.00" matched to "18". |
| E29 | Issuing reduces stock for stock-tracked goods, and cancelling puts it back. |
| E36, E38 | The invoice list filters by customer. Customer history counts only issued invoices: cancelled ones and drafts are left out. |
| E2, E18 | Every Sales & Billing form, plus HRMS and lead import, shows the server's real message (`getErrorMessage`). |
| E17 | Custom lines (no product) save on quotations and invoices. |
| E16, E30 | Quotations show exact rupees. Round-off prints as "−₹0.40". |
| E8 | Unit is a dropdown: Nos, Pieces, Box, Set, Pack, Dozen, Pair, Hour, Day, Month, Year, Job, Kg, Gram, Tonne, Litre, ml, Meter, Sq. ft, Sq. m (migration `erp/0003`). |
| E25 | Drafts carry a placeholder and show as "Draft". The GST number is assigned only at issue, so deleting a draft leaves no gap. |
| E39 | Raise invoice asks for a due date. Draft invoices can edit date, due date and notes. Draft quotations can edit validity and notes. |
| E40 | Deleting a customer or product that's in use returns a 409 with a readable message. |
| E27 | Issuing asks for confirmation first. |
| E20, E34 | Lines can change only on a draft. "Revise (back to draft)" reopens a sent quotation. "Customer accepted" works from draft too, so it matches convert. |
| E19, E21 | An empty quotation can't be sent or accepted, and an expired one can't be accepted or converted. |
| E13 | Valid-until must be on or after the quotation date. The due date must be on or after the invoice date. |
| E31 | Future payment dates are refused. |
| E33, E32 | Payments can be removed from the Payments list and from the invoice. The cancel message now says to remove payments first. |
| E22, E24, E35 | The order filter lists Open/Fulfilled/Invoiced/Cancelled. Orders have a Cancel action that needs a reason. Cancelling or deleting an order's invoice reopens the order. |
| E23 | Order detail shows Disc and Taxable columns and the CGST/SGST or IGST split. |
| E7 | Customers and products have an Active switch, and inactive ones are hidden from new documents. |
| E14 | The interstate flag is set when the quotation is created. |
| E9, E3, E5 | HSN/SAC must be 4, 6 or 8 digits. Phone numbers are normalised. Duplicate GSTINs are refused, and so are duplicate names without a GSTIN. |
| Polish | The GSTIN field no longer squeezes, and the company name comes from Company Profile. |

**Deploy:** pull, then `python manage.py migrate_schemas` (new `erp/0003`), then rebuild the frontend. Then, before issuing any invoice, open **Settings → Company Profile** and set the real company name, GSTIN and state.
