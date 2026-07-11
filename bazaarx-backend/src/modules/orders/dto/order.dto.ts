import { ApiProperty, ApiPropertyOptional } from '@nestjs/swagger';
import { IsUUID, IsEnum, IsOptional, IsString, Length } from 'class-validator';
import { PaymentMethod } from '../entities/order.entity';
import { OrderItemStatus } from '../entities/order-item.entity';

export class CheckoutDto {
  @ApiProperty({ description: 'Saved address id to deliver to' })
  @IsUUID()
  addressId: string;

  @ApiProperty({ enum: PaymentMethod, example: PaymentMethod.COD })
  @IsEnum(PaymentMethod)
  paymentMethod: PaymentMethod;

  @ApiPropertyOptional({ description: 'Optional coupon code' })
  @IsOptional()
  @IsString()
  couponCode?: string;
}

export class CancelOrderItemDto {
  @ApiProperty({ example: 'Ordered by mistake' })
  @IsString()
  @Length(3, 500)
  reason: string;
}

export class UpdateItemStatusDto {
  @ApiProperty({
    enum: [
      OrderItemStatus.CONFIRMED,
      OrderItemStatus.PACKED,
      OrderItemStatus.SHIPPED,
      OrderItemStatus.OUT_FOR_DELIVERY,
      OrderItemStatus.DELIVERED,
    ],
  })
  @IsEnum(OrderItemStatus)
  status: OrderItemStatus;

  @ApiPropertyOptional({ description: 'AWB / tracking number (required when shipping)' })
  @IsOptional()
  @IsString()
  awbNumber?: string;
}
