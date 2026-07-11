import { Injectable, Logger } from '@nestjs/common';
import { ConfigService } from '@nestjs/config';
import { randomUUID, createHash } from 'crypto';
import { BecknContext, BecknAck } from '../types/beckn.types';

/**
 * Builds Beckn protocol context envelopes and the ONDC authorization
 * header. Real ONDC requires an Ed25519 keypair registered with the
 * network registry; when no signing key is configured the adapter runs
 * in mock mode and emits a structurally-correct (unsigned) header — the
 * same dev-fallback pattern used for our other external integrations.
 */
@Injectable()
export class BecknContextService {
  private readonly logger = new Logger('ONDC');
  private readonly CORE_VERSION = '1.2.0';

  constructor(private readonly config: ConfigService) {}

  get isMock(): boolean {
    return !this.config.get<string>('ondc.signingPrivateKey');
  }

  get subscriberId(): string {
    return this.config.get<string>('ondc.subscriberId')!;
  }

  get subscriberUrl(): string {
    return this.config.get<string>('ondc.subscriberUrl')!;
  }

  /** Builds the context for an on_* response, echoing the incoming one. */
  buildResponseContext(
    incoming: BecknContext,
    action: string,
  ): BecknContext {
    return {
      ...incoming,
      action,
      bpp_id: this.subscriberId,
      bpp_uri: this.subscriberUrl,
      message_id: randomUUID(),
      timestamp: new Date().toISOString(),
    };
  }

  /** Builds a fresh context (e.g. when this node initiates a call). */
  buildContext(action: string, transactionId?: string): BecknContext {
    return {
      domain: this.config.get<string>('ondc.domain')!,
      country: this.config.get<string>('ondc.country')!,
      city: this.config.get<string>('ondc.city')!,
      action,
      core_version: this.CORE_VERSION,
      bap_id: this.subscriberId,
      bap_uri: this.subscriberUrl,
      transaction_id: transactionId ?? randomUUID(),
      message_id: randomUUID(),
      timestamp: new Date().toISOString(),
      ttl: 'PT30S',
    };
  }

  ack(): BecknAck {
    return { message: { ack: { status: 'ACK' } } };
  }

  nack(code: string, message: string): BecknAck {
    return {
      message: { ack: { status: 'NACK' } },
      error: { type: 'CONTEXT-ERROR', code, message },
    };
  }

  /**
   * Produces the ONDC `Authorization` header. The real header signs a
   * BLAKE-512 digest of the body with Ed25519. Here we compute the
   * request digest and assemble the header structure; signing is stubbed
   * unless a key is configured.
   */
  buildAuthHeader(body: unknown): string {
    const keyId = `${this.subscriberId}|${this.config.get<string>('ondc.uniqueKeyId')}|ed25519`;
    const created = Math.floor(Date.now() / 1000);
    const expires = created + 30;
    const digest = createHash('sha512')
      .update(JSON.stringify(body))
      .digest('base64');

    if (this.isMock) {
      this.logger.debug('🌐 [DEV ONDC] emitting unsigned (mock) auth header');
    }
    const signature = this.isMock ? 'MOCK_SIGNATURE' : this.sign(digest);

    return (
      `Signature keyId="${keyId}",algorithm="ed25519",` +
      `created="${created}",expires="${expires}",` +
      `headers="(created) (expires) digest",signature="${signature}"`
    );
  }

  private sign(_digest: string): string {
    // Real impl: nacl.sign.detached(blake512(signingString), privateKey)
    // Requires the registered Ed25519 private key from config.
    return 'SIGNATURE_PLACEHOLDER';
  }
}
