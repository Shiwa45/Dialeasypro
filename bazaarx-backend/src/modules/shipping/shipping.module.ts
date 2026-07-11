import { Module } from '@nestjs/common';
import { TypeOrmModule } from '@nestjs/typeorm';
import { Shipment } from './entities/shipment.entity';
import { Order } from '../orders/entities/order.entity';
import { OrderItem } from '../orders/entities/order-item.entity';
import { ShiprocketService } from './services/shiprocket.service';
import { ShippingService } from './services/shipping.service';
import { ShippingController } from './controllers/shipping.controller';

/**
 * Logistics (Shiprocket). Uses Order/OrderItem repos directly to update
 * item status on shipment/delivery — no dependency on OrdersModule.
 */
@Module({
  imports: [TypeOrmModule.forFeature([Shipment, Order, OrderItem])],
  controllers: [ShippingController],
  providers: [ShiprocketService, ShippingService],
  exports: [ShippingService, ShiprocketService],
})
export class ShippingModule {}
