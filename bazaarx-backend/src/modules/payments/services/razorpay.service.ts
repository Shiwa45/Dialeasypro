import { Injectable, Logger } from '@nestjs/common';
import { ConfigService } from '@nestjs/config';
import { createHmac, randomBytes, timingSafeEqual } from 'crypto';

export interface GatewayOrder {
  gatewayOrderId: string;
  amount: number;
  currency: string;
  keyId: string;
  isMock: boolean;
}

/**
 * Razorpay integration.
 *
 * When credentials are configured, it calls the real Razorpay REST API.
 * When they're absent (local dev), it runs in MOCK mode: it fabricates a
 * gateway order id and can self-sign payments, so the entire checkout →
 * pay → verify flow is testable without a Razorpay account.
 *
 * Signature verification (the security-critical part) uses the SAME real
 * HMAC-SHA256 logic in both modes.
 */
@Injectable()
export class RazorpayService {
  private readonly logger = new Logger('Razorpay');

  constructor(private readonly config: ConfigService) {}

  private get keyId() {
    return this.config.get<string>('razorpay.keyId') || '';
  }
  private get keySecret() {
    return this.config.get<string>('razorpay.keySecret') || '';
  }
  private get webhookSecret() {
    return this.config.get<string>('razorpay.webhookSecret') || '';
  }

  get isMock(): boolean {
    return !this.keyId || !this.keySecret;
  }

  /** Creates a gateway order to start a payment. */
  async createOrder(
    amountPaise: number,
    receipt: string,
  ): Promise<GatewayOrder> {
    if (this.isMock) {
      const gatewayOrderId = `order_MOCK${randomBytes(8).toString('hex')}`;
      this.logger.debug(
        `[MOCK] Created gateway order ${gatewayOrderId} for ₹${amountPaise / 100}`,
      );
      return {
        gatewayOrderId,
        amount: amountPaise,
        currency: 'INR',
        keyId: 'rzp_test_mock',
        isMock: true,
      };
    }

    const res = await fetch('https://api.razorpay.com/v1/orders', {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
        Authorization:
          'Basic ' +
          Buffer.from(`${this.keyId}:${this.keySecret}`).toString('base64'),
      },
      body: JSON.stringify({
        amount: amountPaise,
        currency: 'INR',
        receipt,
      }),
    });
    if (!res.ok) {
      const body = await res.text();
      throw new Error(`Razorpay order creation failed (${res.status}): ${body}`);
    }
    const data = (await res.json()) as { id: string };
    return {
      gatewayOrderId: data.id,
      amount: amountPaise,
      currency: 'INR',
      keyId: this.keyId,
      isMock: false,
    };
  }

  /**
   * Verifies a payment signature:
   *   HMAC_SHA256(order_id + "|" + payment_id, key_secret) === signature
   * Uses a constant-time comparison to avoid timing attacks.
   */
  verifyPaymentSignature(
    gatewayOrderId: string,
    gatewayPaymentId: string,
    signature: string,
  ): boolean {
    const secret = this.keySecret || 'mock_secret';
    const expected = createHmac('sha256', secret)
      .update(`${gatewayOrderId}|${gatewayPaymentId}`)
      .digest('hex');
    return this.safeEqual(expected, signature);
  }

  /** Verifies a Razorpay webhook body signature. */
  verifyWebhookSignature(rawBody: string, signature: string): boolean {
    const secret = this.webhookSecret || 'mock_webhook_secret';
    const expected = createHmac('sha256', secret)
      .update(rawBody)
      .digest('hex');
    return this.safeEqual(expected, signature);
  }

  /**
   * Issues a refund against a captured payment.
   * Real Razorpay refund API when configured; mock id otherwise.
   */
  async refund(
    gatewayPaymentId: string,
    amountPaise: number,
  ): Promise<{ refundId: string; isMock: boolean }> {
    if (this.isMock) {
      const refundId = `rfnd_MOCK${randomBytes(8).toString('hex')}`;
      this.logger.debug(
        `[MOCK] Refund ${refundId} of ₹${amountPaise / 100} on ${gatewayPaymentId}`,
      );
      return { refundId, isMock: true };
    }
    const res = await fetch(
      `https://api.razorpay.com/v1/payments/${gatewayPaymentId}/refund`,
      {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
          Authorization:
            'Basic ' +
            Buffer.from(`${this.keyId}:${this.keySecret}`).toString('base64'),
        },
        body: JSON.stringify({ amount: amountPaise }),
      },
    );
    if (!res.ok) {
      const body = await res.text();
      throw new Error(`Razorpay refund failed (${res.status}): ${body}`);
    }
    const data = (await res.json()) as { id: string };
    return { refundId: data.id, isMock: false };
  }

  /**
   * MOCK ONLY: produces the signature a client would return after paying,
   * so automated tests can exercise the verify path. Never used in prod.
   */
  mockSignPayment(gatewayOrderId: string, gatewayPaymentId: string): string {
    return createHmac('sha256', this.keySecret || 'mock_secret')
      .update(`${gatewayOrderId}|${gatewayPaymentId}`)
      .digest('hex');
  }

  private safeEqual(a: string, b: string): boolean {
    const ba = Buffer.from(a);
    const bb = Buffer.from(b);
    if (ba.length !== bb.length) return false;
    return timingSafeEqual(ba, bb);
  }
}
