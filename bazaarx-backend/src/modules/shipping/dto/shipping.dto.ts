import { ApiProperty, ApiPropertyOptional } from '@nestjs/swagger';
import { Type } from 'class-transformer';
import { IsString, Length, IsOptional, IsInt, Min, IsBoolean } from 'class-validator';

export class ServiceabilityDto {
  @ApiProperty({ example: '560001', description: 'Delivery pincode' })
  @IsString()
  @Length(6, 6)
  deliveryPincode: string;

  @ApiPropertyOptional({ example: 500, description: 'Weight in grams' })
  @IsOptional()
  @Type(() => Number)
  @IsInt()
  @Min(1)
  weightGrams?: number;

  @ApiPropertyOptional({ example: true })
  @IsOptional()
  @Type(() => Boolean)
  @IsBoolean()
  cod?: boolean;
}
