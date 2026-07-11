import { Module } from '@nestjs/common';
import { TypeOrmModule } from '@nestjs/typeorm';
import { Product } from '../catalog/entities/product.entity';
import { OrderItem } from '../orders/entities/order-item.entity';
import { RecommendationService } from './services/recommendation.service';
import { RecommendationController } from './controllers/recommendation.controller';

/**
 * Recommendations: query-driven heuristics over the catalogue and real
 * purchase data (co-purchase, personalization, trending) + Redis-backed
 * recently-viewed. No new tables.
 */
@Module({
  imports: [TypeOrmModule.forFeature([Product, OrderItem])],
  controllers: [RecommendationController],
  providers: [RecommendationService],
  exports: [RecommendationService],
})
export class RecommendationsModule {}
