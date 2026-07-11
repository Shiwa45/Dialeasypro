import { ApiProperty } from '@nestjs/swagger';
import { Type } from 'class-transformer';
import { IsInt, Min, IsString, Length } from 'class-validator';

export class TopupDto {
  @ApiProperty({ example: 50000, description: 'Amount in paise (min ₹10)' })
  @Type(() => Number)
  @IsInt()
  @Min(1000)
  amount: number;
}

export class VerifyTopupDto {
  @ApiProperty()
  @IsString()
  @Length(3, 100)
  gatewayOrderId: string;

  @ApiProperty()
  @IsString()
  @Length(3, 100)
  gatewayPaymentId: string;

  @ApiProperty()
  @IsString()
  @Length(3, 256)
  signature: string;
}

export class MockPayTopupDto {
  @ApiProperty()
  @IsString()
  @Length(3, 100)
  gatewayOrderId: string;
}

export class RepayBnplDto {
  @ApiProperty({ example: 100000, description: 'Amount in paise' })
  @Type(() => Number)
  @IsInt()
  @Min(1)
  amount: number;
}
