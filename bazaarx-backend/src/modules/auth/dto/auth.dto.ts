import { ApiProperty, ApiPropertyOptional } from '@nestjs/swagger';
import {
  IsString,
  IsOptional,
  IsEmail,
  Length,
  MinLength,
} from 'class-validator';
import { IsIndianMobile } from '../../../common/decorators/is-indian-mobile.decorator';

export class SendOtpDto {
  @ApiProperty({ example: '9876543210', description: 'Indian mobile number' })
  @IsIndianMobile()
  mobile: string;
}

export class VerifyOtpDto {
  @ApiProperty({ example: '9876543210' })
  @IsIndianMobile()
  mobile: string;

  @ApiProperty({ example: '123456', description: '6-digit OTP' })
  @IsString()
  @Length(4, 8)
  otp: string;

  // Optional profile fields for first-time registration on verify
  @ApiPropertyOptional({ example: 'Ravi' })
  @IsOptional()
  @IsString()
  firstName?: string;

  @ApiPropertyOptional({ example: 'Kumar' })
  @IsOptional()
  @IsString()
  lastName?: string;

  @ApiPropertyOptional({ example: 'ravi@example.com' })
  @IsOptional()
  @IsEmail()
  email?: string;
}

export class RefreshTokenDto {
  @ApiProperty({ description: 'A valid refresh token' })
  @IsString()
  @MinLength(10)
  refreshToken: string;
}
