/**
 * Minimal Beckn/ONDC protocol typings used by the adapter. The real
 * spec is far larger; these cover the search → confirm → status flow.
 */
export interface BecknContext {
  domain: string;
  country: string;
  city: string;
  action: string;
  core_version: string;
  bap_id: string;
  bap_uri: string;
  bpp_id?: string;
  bpp_uri?: string;
  transaction_id: string;
  message_id: string;
  timestamp: string;
  ttl?: string;
}

export interface BecknAck {
  message: { ack: { status: 'ACK' | 'NACK' } };
  error?: { type: string; code: string; message: string };
}

export interface BecknEnvelope<T = unknown> {
  context: BecknContext;
  message: T;
}
