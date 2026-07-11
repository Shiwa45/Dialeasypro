import { Injectable } from '@nestjs/common';
import { OtpService } from './services/otp.service';
import { TokenService, TokenPair } from './services/token.service';
import { UsersService } from '../users/users.service';
import { User } from '../users/entities/user.entity';
import { normalizeIndianMobile } from '../../common/decorators/is-indian-mobile.decorator';
import { SendOtpDto, VerifyOtpDto } from './dto/auth.dto';

export interface AuthResult {
  user: {
    id: string;
    mobile: string;
    email?: string;
    firstName?: string;
    lastName?: string;
    role: string;
    isNewUser: boolean;
  };
  tokens: TokenPair;
}

/**
 * OTP-first authentication flow:
 *   1. sendOtp  → generate + SMS a code
 *   2. verifyOtp → validate code; create user if first time; issue JWTs
 *
 * Mobile is normalized to bare 10 digits before any lookup/store,
 * so "+919876543210", "09876543210", and "9876543210" are one user.
 */
@Injectable()
export class AuthService {
  constructor(
    private readonly otp: OtpService,
    private readonly tokens: TokenService,
    private readonly users: UsersService,
  ) {}

  async sendOtp(dto: SendOtpDto): Promise<{ resendAfterSeconds: number }> {
    const mobile = normalizeIndianMobile(dto.mobile);
    return this.otp.sendOtp(mobile);
  }

  async verifyOtpAndAuth(dto: VerifyOtpDto): Promise<AuthResult> {
    const mobile = normalizeIndianMobile(dto.mobile);

    // Throws if invalid/expired/too-many-attempts
    await this.otp.verifyOtp(mobile, dto.otp);

    let user = await this.users.findByMobile(mobile);
    let isNewUser = false;

    if (!user) {
      // First-time login = registration
      user = await this.users.create({
        mobile,
        firstName: dto.firstName,
        lastName: dto.lastName,
        email: dto.email,
        isMobileVerified: true,
      });
      isNewUser = true;
    } else if (!user.isMobileVerified) {
      await this.users.markMobileVerified(user.id);
    }

    await this.users.updateLastLogin(user.id);
    const tokens = await this.tokens.issueTokenPair(user.id, user.role);

    return { user: this.sanitize(user, isNewUser), tokens };
  }

  async refresh(refreshToken: string): Promise<TokenPair> {
    return this.tokens.rotateRefreshToken(refreshToken);
  }

  async logout(refreshToken: string): Promise<void> {
    await this.tokens.revokeRefreshToken(refreshToken);
  }

  async logoutEverywhere(userId: string): Promise<void> {
    await this.tokens.revokeAllForUser(userId);
  }

  private sanitize(user: User, isNewUser: boolean) {
    return {
      id: user.id,
      mobile: user.mobile,
      email: user.email,
      firstName: user.firstName,
      lastName: user.lastName,
      role: user.role,
      isNewUser,
    };
  }
}
