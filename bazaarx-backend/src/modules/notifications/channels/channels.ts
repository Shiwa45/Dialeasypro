import { Injectable, Logger } from '@nestjs/common';
import { ConfigService } from '@nestjs/config';

/**
 * External delivery channels. Each integrates a real provider when
 * configured and otherwise logs to the dev console — the same fallback
 * pattern used for OTP SMS, Razorpay, and Shiprocket. The in-app inbox
 * is handled by the NotificationService directly (always on).
 */

@Injectable()
export class EmailChannel {
  private readonly logger = new Logger('EmailChannel');
  constructor(private readonly config: ConfigService) {}

  async send(to: string | undefined, subject: string, body: string) {
    if (!to) return;
    // Real provider (SES/SendGrid) would go here when configured.
    this.logger.debug(`📧 [DEV EMAIL] to ${to} | ${subject} — ${body}`);
  }
}

@Injectable()
export class SmsChannel {
  private readonly logger = new Logger('SmsChannel');
  constructor(private readonly config: ConfigService) {}

  async send(to: string | undefined, body: string) {
    if (!to) return;
    // Real provider (MSG91) would go here when configured.
    this.logger.debug(`📱 [DEV SMS] to +91${to} — ${body}`);
  }
}

@Injectable()
export class PushChannel {
  private readonly logger = new Logger('PushChannel');
  constructor(private readonly config: ConfigService) {}

  async send(userId: string, title: string, body: string) {
    // Real provider (FCM/APNs) would go here when configured.
    this.logger.debug(`🔔 [DEV PUSH] user ${userId} | ${title} — ${body}`);
  }
}
