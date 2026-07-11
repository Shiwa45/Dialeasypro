import { ApiProperty } from '@nestjs/swagger';
import { IsString, Length } from 'class-validator';

export class VerifyPaymentDto {
  @ApiProperty({ example: 'order_XXXXXXXX' })
  @IsString()
  @Length(3, 100)
  gatewayOrderId: string;

  @ApiProperty({ example: 'pay_XXXXXXXX' })
  @IsString()
  @Length(3, 100)
  gatewayPaymentId: string;

  @ApiProperty({ description: 'razorpay_signature returned to the client' })
  @IsString()
  @Length(3, 256)
  signature: string;
}
