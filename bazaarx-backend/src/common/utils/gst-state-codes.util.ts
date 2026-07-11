/**
 * Indian GST state codes (first 2 digits of a GSTIN).
 * Used to determine place of supply and whether a transaction is
 * intra-state (CGST + SGST) or inter-state (IGST).
 */
export const GST_STATE_CODES: Record<string, string> = {
  '01': 'Jammu and Kashmir',
  '02': 'Himachal Pradesh',
  '03': 'Punjab',
  '04': 'Chandigarh',
  '05': 'Uttarakhand',
  '06': 'Haryana',
  '07': 'Delhi',
  '08': 'Rajasthan',
  '09': 'Uttar Pradesh',
  '10': 'Bihar',
  '11': 'Sikkim',
  '12': 'Arunachal Pradesh',
  '13': 'Nagaland',
  '14': 'Manipur',
  '15': 'Mizoram',
  '16': 'Tripura',
  '17': 'Meghalaya',
  '18': 'Assam',
  '19': 'West Bengal',
  '20': 'Jharkhand',
  '21': 'Odisha',
  '22': 'Chhattisgarh',
  '23': 'Madhya Pradesh',
  '24': 'Gujarat',
  '26': 'Dadra and Nagar Haveli and Daman and Diu',
  '27': 'Maharashtra',
  '28': 'Andhra Pradesh',
  '29': 'Karnataka',
  '30': 'Goa',
  '31': 'Lakshadweep',
  '32': 'Kerala',
  '33': 'Tamil Nadu',
  '34': 'Puducherry',
  '35': 'Andaman and Nicobar Islands',
  '36': 'Telangana',
  '37': 'Andhra Pradesh',
  '38': 'Ladakh',
};

/** Returns the state name for a GSTIN (from its first 2 digits). */
export function stateFromGstin(gstin: string): string {
  return GST_STATE_CODES[gstin.slice(0, 2)] ?? 'Unknown';
}

/** Normalizes a state name for loose comparison. */
export function normalizeState(state: string): string {
  return state.trim().toLowerCase().replace(/\s+/g, ' ');
}

/**
 * Intra-state if the seller's GSTIN state matches the buyer's state.
 * Intra → CGST + SGST (split). Inter → IGST (full).
 */
export function isIntraState(sellerGstin: string, buyerState: string): boolean {
  return normalizeState(stateFromGstin(sellerGstin)) === normalizeState(buyerState);
}
