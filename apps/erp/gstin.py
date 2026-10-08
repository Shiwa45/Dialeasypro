"""
TeleCRM Backend — apps/erp/gstin.py

GSTIN validation and the state it belongs to.

A GSTIN is 15 characters: 2-digit state code, 10-character PAN, entity
number, the letter Z, and a check character computed over the first 14
(mod-36, alternating weights 1/2). Only the length used to be checked, so a
Delhi GSTIN could be saved against a Maharashtra customer — and a customer
with a GSTIN but no state was taxed as intra-state whatever its real state.
"""
import re

GSTIN_RE = re.compile(r"^[0-9]{2}[A-Z]{5}[0-9]{4}[A-Z][1-9A-Z]Z[0-9A-Z]$")
_CHARS = "0123456789ABCDEFGHIJKLMNOPQRSTUVWXYZ"

# GST state code (first two digits of a GSTIN) → the 2-letter code used for
# place of supply (apps.core.constants.INDIAN_STATES).
GST_STATE_BY_NUMBER = {
    "01": "JK", "02": "HP", "03": "PB", "04": "CH", "05": "UK", "06": "HR",
    "07": "DL", "08": "RJ", "09": "UP", "10": "BR", "11": "SK", "12": "AR",
    "13": "NL", "14": "MN", "15": "MZ", "16": "TR", "17": "ML", "18": "AS",
    "19": "WB", "20": "JH", "21": "OD", "22": "CG", "23": "MP", "24": "GJ",
    "25": "DN", "26": "DN", "27": "MH", "28": "AP", "29": "KA", "30": "GA",
    "31": "LD", "32": "KL", "33": "TN", "34": "PY", "35": "AN", "36": "TS",
    "37": "AP", "38": "LA",
}


def check_char(first14: str) -> str:
    total = 0
    for i, ch in enumerate(first14):
        value = _CHARS.index(ch) * (2 if i % 2 else 1)
        total += value // 36 + value % 36
    return _CHARS[(36 - total % 36) % 36]


def gstin_problem(gstin: str) -> str:
    """Why this GSTIN is invalid, as a sentence — or ""."""
    g = (gstin or "").strip().upper()
    if not g:
        return ""
    if len(g) != 15:
        return "A GSTIN is exactly 15 characters."
    if not GSTIN_RE.match(g):
        return "That isn't a valid GSTIN format (e.g. 27ABCDE1234F1Z5)."
    if g[:2] not in GST_STATE_BY_NUMBER and g[:2] not in ("97", "99"):
        return f"{g[:2]} is not a GST state code."
    if check_char(g[:14]) != g[14]:
        return "This GSTIN's check character is wrong — please re-check the number."
    return ""


def state_from_gstin(gstin: str) -> str:
    return GST_STATE_BY_NUMBER.get((gstin or "").strip()[:2], "")
