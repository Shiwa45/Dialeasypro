import { Injectable, Logger } from '@nestjs/common';
import { ConfigService } from '@nestjs/config';

/**
 * Sends transactional SMS via MSG91 (India).
 *
 * In any non-production environment, OR when MSG91 credentials are
 * not configured, it falls back to logging the OTP to the console —
 * so the full auth flow is testable locally with zero SMS cost.
 */
@Injectable()
export class SmsService {
  private readonly logger = new Logger('SmsService');

  constructor(private readonly config: ConfigService) {}

  async sendOtp(mobile: string, code: string): Promise<void> {
    const authKey = this.config.get<string>('sms.msg91AuthKey');
    const isProd = this.config.get<string>('app.env') === 'production';

    // Dev / unconfigured → console fallback
    if (!authKey || !isProd) {
      this.logger.debug(
        `📱 [DEV SMS] OTP for +91${mobile} is: ${code} (would send via MSG91 in prod)`,
      );
      return;
    }

    await this.sendViaMsg91(mobile, code);
  }

  private async sendViaMsg91(mobile: string, code: string): Promise<void> {
    const authKey = this.config.get<string>('sms.msg91AuthKey')!;
    const templateId = this.config.get<string>('sms.msg91TemplateId')!;

    try {
      // MSG91 OTP API: https://control.msg91.com/api/v5/otp
      const res = await fetch(
        `https://control.msg91.com/api/v5/otp?template_id=${templateId}&mobile=91${mobile}&otp=${code}`,
        {
          method: 'POST',
          headers: {
            authkey: authKey,
            'Content-Type': 'application/json',
          },
        },
      );

      if (!res.ok) {
        const body = await res.text();
        throw new Error(`MSG91 responded ${res.status}: ${body}`);
      }

      this.logger.log(`OTP SMS sent to +91${mobile}`);
    } catch (err) {
      this.logger.error(
        `Failed to send OTP SMS to +91${mobile}: ${(err as Error).message}`,
      );
      // Re-throw so caller knows delivery failed
      throw err;
    }
  }
}
