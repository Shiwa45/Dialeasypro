import { ApiProperty, ApiPropertyOptional } from '@nestjs/swagger';
import { Type } from 'class-transformer';
import {
  IsString,
  Length,
  IsEnum,
  IsInt,
  Min,
  IsOptional,
  IsUUID,
  IsBoolean,
  IsDateString,
} from 'class-validator';
import { DiscountType, CouponScope } from '../entities/coupon.entity';

export class CreateCouponDto {
  @ApiProperty({ example: 'SAVE10' })
  @IsString()
  @Length(3, 40)
  code: string;

  @ApiPropertyOptional()
  @IsOptional()
  @IsString()
  @Length(0, 200)
  description?: string;

  @ApiProperty({ enum: DiscountType })
  @IsEnum(DiscountType)
  discountType: DiscountType;

  @ApiProperty({ description: 'Percent (10) or flat paise', example: 10 })
  @Type(() => Number)
  @IsInt()
  @Min(1)
  discountValue: number;

  @ApiPropertyOptional({ description: 'Cap for % discounts (paise)' })
  @IsOptional()
  @Type(() => Number)
  @IsInt()
  @Min(0)
  maxDiscountAmount?: number;

  @ApiPropertyOptional({ default: 0, description: 'Min cart value (paise)' })
  @IsOptional()
  @Type(() => Number)
  @IsInt()
  @Min(0)
  minCartValue?: number;

  @ApiPropertyOptional({ enum: CouponScope, default: CouponScope.ALL })
  @IsOptional()
  @IsEnum(CouponScope)
  scope?: CouponScope;

  @ApiPropertyOptional({ description: 'categoryId or sellerId when scoped' })
  @IsOptional()
  @IsUUID()
  scopeId?: string;

  @ApiPropertyOptional({ description: 'Global usage cap' })
  @IsOptional()
  @Type(() => Number)
  @IsInt()
  @Min(1)
  usageLimit?: number;

  @ApiPropertyOptional({ default: 1 })
  @IsOptional()
  @Type(() => Number)
  @IsInt()
  @Min(1)
  perUserLimit?: number;

  @ApiProperty({ example: '2026-06-01T00:00:00.000Z' })
  @IsDateString()
  validFrom: string;

  @ApiProperty({ example: '2026-12-31T23:59:59.000Z' })
  @IsDateString()
  validUntil: string;
}

export class ValidateCouponDto {
  @ApiProperty({ example: 'SAVE10' })
  @IsString()
  @Length(3, 40)
  code: string;
}
