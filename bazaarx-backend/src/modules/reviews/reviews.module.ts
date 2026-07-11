import { Module } from '@nestjs/common';
import { TypeOrmModule } from '@nestjs/typeorm';
import { Review } from './entities/review.entity';
import { ReviewVote } from './entities/review-vote.entity';
import { Product } from '../catalog/entities/product.entity';
import { OrderItem } from '../orders/entities/order-item.entity';
import { ReviewService } from './services/review.service';
import { ReviewController } from './controllers/review.controller';

/**
 * Reviews & ratings. Recomputes product avgRating/reviewCount on every
 * change and emits product.published so the search index stays in sync.
 */
@Module({
  imports: [TypeOrmModule.forFeature([Review, ReviewVote, Product, OrderItem])],
  controllers: [ReviewController],
  providers: [ReviewService],
  exports: [ReviewService],
})
export class ReviewsModule {}
