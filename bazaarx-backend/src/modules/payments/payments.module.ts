import { Module } from '@nestjs/common';
import { TypeOrmModule } from '@nestjs/typeorm';
import { Payment } from './entities/payment.entity';
import { Order } from '../orders/entities/order.entity';
import { OrderItem } from '../orders/entities/order-item.entity';
import { ProductVariant } from '../catalog/entities/product-variant.entity';
import { PaymentService } from './services/payment.service';
import { RazorpayService } from './services/razorpay.service';
import { PaymentController } from './controllers/payment.controller';

/**
 * Payments. Uses Order/OrderItem/ProductVariant repos directly (not
 * OrderService) to avoid a circular dependency with OrdersModule —
 * OrdersModule imports THIS module for PaymentService.
 */
@Module({
  imports: [
    TypeOrmModule.forFeature([Payment, Order, OrderItem, ProductVariant]),
  ],
  controllers: [PaymentController],
  providers: [PaymentService, RazorpayService],
  exports: [PaymentService, RazorpayService],
})
export class PaymentsModule {}
