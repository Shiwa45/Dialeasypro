import { Module } from '@nestjs/common';
import { TypeOrmModule } from '@nestjs/typeorm';
import { Return } from './entities/return.entity';
import { Order } from '../orders/entities/order.entity';
import { OrderItem } from '../orders/entities/order-item.entity';
import { ProductVariant } from '../catalog/entities/product-variant.entity';
import { ReturnService } from './services/return.service';
import { ReturnController } from './controllers/return.controller';
import { PaymentsModule } from '../payments/payments.module';
import { ShippingModule } from '../shipping/shipping.module';
import { WalletModule } from '../wallet/wallet.module';

/**
 * Returns & refunds. Imports PaymentsModule (gateway refunds) and
 * ShippingModule (reverse pickups). Uses order/item/variant repos
 * directly to update status and restock.
 */
@Module({
  imports: [
    TypeOrmModule.forFeature([Return, Order, OrderItem, ProductVariant]),
    PaymentsModule,
    ShippingModule,
    WalletModule,
  ],
  controllers: [ReturnController],
  providers: [ReturnService],
  exports: [ReturnService],
})
export class ReturnsModule {}
