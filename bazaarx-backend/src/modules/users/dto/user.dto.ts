import { ApiPropertyOptional, ApiProperty, PartialType } from '@nestjs/swagger';
import {
  IsString,
  IsOptional,
  IsEmail,
  IsEnum,
  IsDateString,
  Length,
  Matches,
  IsLatitude,
  IsLongitude,
  IsBoolean,
} from 'class-validator';
import { Gender, Language } from '../entities/user.entity';
import { AddressLabel } from '../entities/address.entity';
import { IsIndianMobile } from '../../../common/decorators/is-indian-mobile.decorator';

export class UpdateProfileDto {
  @ApiPropertyOptional()
  @IsOptional()
  @IsString()
  @Length(1, 100)
  firstName?: string;

  @ApiPropertyOptional()
  @IsOptional()
  @IsString()
  @Length(1, 100)
  lastName?: string;

  @ApiPropertyOptional({ example: 'ravi@example.com' })
  @IsOptional()
  @IsEmail()
  email?: string;

  @ApiPropertyOptional({ example: '1995-08-15' })
  @IsOptional()
  @IsDateString()
  dateOfBirth?: string;

  @ApiPropertyOptional({ enum: Gender })
  @IsOptional()
  @IsEnum(Gender)
  gender?: Gender;

  @ApiPropertyOptional({ enum: Language })
  @IsOptional()
  @IsEnum(Language)
  preferredLanguage?: Language;
}

export class CreateAddressDto {
  @ApiPropertyOptional({ enum: AddressLabel, default: AddressLabel.HOME })
  @IsOptional()
  @IsEnum(AddressLabel)
  label?: AddressLabel;

  @ApiProperty({ example: 'Ravi Kumar' })
  @IsString()
  @Length(2, 100)
  name: string;

  @ApiProperty({ example: '9876543210' })
  @IsIndianMobile()
  mobile: string;

  @ApiProperty({ example: 'Flat 402, Sunrise Apartments' })
  @IsString()
  @Length(3, 255)
  line1: string;

  @ApiPropertyOptional({ example: 'MG Road' })
  @IsOptional()
  @IsString()
  @Length(0, 255)
  line2?: string;

  @ApiProperty({ example: 'Bengaluru' })
  @IsString()
  @Length(2, 100)
  city: string;

  @ApiProperty({ example: 'Karnataka' })
  @IsString()
  @Length(2, 100)
  state: string;

  @ApiProperty({ example: '560001', description: '6-digit Indian pincode' })
  @Matches(/^[1-9][0-9]{5}$/, { message: 'pincode must be a valid 6-digit Indian pincode' })
  pincode: string;

  @ApiPropertyOptional({ example: 'Near Metro Station' })
  @IsOptional()
  @IsString()
  @Length(0, 255)
  landmark?: string;

  @ApiPropertyOptional({ example: 12.9716 })
  @IsOptional()
  @IsLatitude()
  latitude?: number;

  @ApiPropertyOptional({ example: 77.5946 })
  @IsOptional()
  @IsLongitude()
  longitude?: number;

  @ApiPropertyOptional({ default: false })
  @IsOptional()
  @IsBoolean()
  isDefault?: boolean;
}

export class UpdateAddressDto extends PartialType(CreateAddressDto) {}
