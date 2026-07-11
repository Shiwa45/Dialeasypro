import { Module } from '@nestjs/common';
import { TypeOrmModule } from '@nestjs/typeorm';
import { Order } from './entities/order.entity';
import { OrderItem } from './entities/order-item.entity';
import { ProductVariant } from '../catalog/entities/product-variant.entity';
import { Category } from '../catalog/entities/category.entity';
import { CheckoutService } from './services/checkout.service';
import { OrderService } from './services/order.service';
import { OrderController } from './controllers/order.controller';
import { CartModule } from '../cart/cart.module';
import { UsersModule } from '../users/users.module';
import { PaymentsModule } from '../payments/payments.module';
import { PromotionsModule } from '../promotions/promotions.module';
import { WalletModule } from '../wallet/wallet.module';

@Module({
  imports: [
    TypeOrmModule.forFeature([Order, OrderItem, ProductVariant, Category]),
    CartModule,
    UsersModule, // provides AddressService
    PaymentsModule, // provides PaymentService
    PromotionsModule, // provides CouponService
    WalletModule, // provides WalletService
  ],
  controllers: [OrderController],
  providers: [CheckoutService, OrderService],
  exports: [CheckoutService, OrderService],
})
export class OrdersModule {}
