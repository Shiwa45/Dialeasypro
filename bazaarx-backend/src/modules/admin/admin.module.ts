import { Module } from '@nestjs/common';
import { TypeOrmModule } from '@nestjs/typeorm';
import { User } from '../users/entities/user.entity';
import { Seller } from '../sellers/entities/seller.entity';
import { Product } from '../catalog/entities/product.entity';
import { Order } from '../orders/entities/order.entity';
import { OrderItem } from '../orders/entities/order-item.entity';
import { Review } from '../reviews/entities/review.entity';
import { AdminService } from './services/admin.service';
import { AdminController } from './controllers/admin.controller';

/**
 * Admin panel: platform oversight, user management, moderation queues,
 * and review moderation. Admin-only via RolesGuard. Suspension toggles
 * User.isActive, which auth already enforces — no schema change.
 */
@Module({
  imports: [
    TypeOrmModule.forFeature([User, Seller, Product, Order, OrderItem, Review]),
  ],
  controllers: [AdminController],
  providers: [AdminService],
  exports: [AdminService],
})
export class AdminModule {}
