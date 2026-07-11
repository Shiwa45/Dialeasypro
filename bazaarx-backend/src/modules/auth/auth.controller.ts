import {
  Body,
  Controller,
  Post,
  Get,
  Version,
  HttpCode,
  HttpStatus,
} from '@nestjs/common';
import { ApiTags, ApiOperation, ApiBearerAuth } from '@nestjs/swagger';
import { AuthService } from './auth.service';
import { SendOtpDto, VerifyOtpDto, RefreshTokenDto } from './dto/auth.dto';
import { Public } from './decorators/public.decorator';
import {
  CurrentUser,
  AuthenticatedUser,
} from './decorators/current-user.decorator';

@ApiTags('Auth')
@Controller('auth')
export class AuthController {
  constructor(private readonly auth: AuthService) {}

  @Public()
  @Post('send-otp')
  @Version('1')
  @HttpCode(HttpStatus.OK)
  @ApiOperation({ summary: 'Send an OTP to a mobile number' })
  async sendOtp(@Body() dto: SendOtpDto) {
    const result = await this.auth.sendOtp(dto);
    return { data: result, message: 'OTP sent successfully' };
  }

  @Public()
  @Post('verify-otp')
  @Version('1')
  @HttpCode(HttpStatus.OK)
  @ApiOperation({ summary: 'Verify OTP, register if new, return JWT tokens' })
  async verifyOtp(@Body() dto: VerifyOtpDto) {
    const result = await this.auth.verifyOtpAndAuth(dto);
    return {
      data: result,
      message: result.user.isNewUser
        ? 'Registration successful'
        : 'Login successful',
    };
  }

  @Public()
  @Post('refresh-token')
  @Version('1')
  @HttpCode(HttpStatus.OK)
  @ApiOperation({ summary: 'Rotate refresh token, get a new token pair' })
  async refresh(@Body() dto: RefreshTokenDto) {
    const tokens = await this.auth.refresh(dto.refreshToken);
    return { data: tokens, message: 'Token refreshed' };
  }

  @Public()
  @Post('logout')
  @Version('1')
  @HttpCode(HttpStatus.OK)
  @ApiOperation({ summary: 'Revoke a refresh token (logout this device)' })
  async logout(@Body() dto: RefreshTokenDto) {
    await this.auth.logout(dto.refreshToken);
    return { data: null, message: 'Logged out' };
  }

  @ApiBearerAuth()
  @Post('logout-all')
  @Version('1')
  @HttpCode(HttpStatus.OK)
  @ApiOperation({ summary: 'Revoke ALL sessions (logout everywhere)' })
  async logoutAll(@CurrentUser('id') userId: string) {
    await this.auth.logoutEverywhere(userId);
    return { data: null, message: 'Logged out from all devices' };
  }

  @ApiBearerAuth()
  @Get('me')
  @Version('1')
  @ApiOperation({ summary: 'Get the currently authenticated user (from token)' })
  me(@CurrentUser() user: AuthenticatedUser) {
    return { data: user, message: 'Authenticated' };
  }
}
