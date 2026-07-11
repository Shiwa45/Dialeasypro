import { Module } from '@nestjs/common';
import { TypeOrmModule } from '@nestjs/typeorm';
import { OrderItem } from '../orders/entities/order-item.entity';
import { Review } from '../reviews/entities/review.entity';
import { Return } from '../returns/entities/return.entity';
import { SellerDashboardService } from './services/seller-dashboard.service';
import { SellerDashboardController } from './controllers/seller-dashboard.controller';

/**
 * Read-only seller analytics aggregated from order items, reviews, and
 * returns. No entities of its own — pure reporting over existing data.
 */
@Module({
  imports: [TypeOrmModule.forFeature([OrderItem, Review, Return])],
  controllers: [SellerDashboardController],
  providers: [SellerDashboardService],
  exports: [SellerDashboardService],
})
export class SellerDashboardModule {}
