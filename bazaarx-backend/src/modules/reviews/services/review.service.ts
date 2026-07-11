import {
  Injectable,
  NotFoundException,
  ForbiddenException,
  BadRequestException,
  ConflictException,
} from '@nestjs/common';
import { InjectRepository } from '@nestjs/typeorm';
import { DataSource, Repository } from 'typeorm';
import { EventEmitter2 } from '@nestjs/event-emitter';
import { Review, ReviewStatus } from '../entities/review.entity';
import { ReviewVote } from '../entities/review-vote.entity';
import { Product, ProductStatus } from '../../catalog/entities/product.entity';
import {
  OrderItem,
  OrderItemStatus,
} from '../../orders/entities/order-item.entity';
import { ProductEvents } from '../../catalog/product.events';
import { CreateReviewDto, UpdateReviewDto } from '../dto/review.dto';
import { paginate } from '../../../common/dto/paginated-result';
import { PaginationQueryDto } from '../../../common/dto/pagination-query.dto';
import { UserRole } from '../../users/entities/user.entity';

@Injectable()
export class ReviewService {
  constructor(
    @InjectRepository(Review)
    private readonly reviewRepo: Repository<Review>,
    @InjectRepository(ReviewVote)
    private readonly voteRepo: Repository<ReviewVote>,
    @InjectRepository(Product)
    private readonly productRepo: Repository<Product>,
    @InjectRepository(OrderItem)
    private readonly itemRepo: Repository<OrderItem>,
    private readonly events: EventEmitter2,
    private readonly dataSource: DataSource,
  ) {}

  // -------- Create / update / delete --------

  async create(
    userId: string,
    productId: string,
    dto: CreateReviewDto,
  ): Promise<Review> {
    const product = await this.productRepo.findOne({ where: { id: productId } });
    if (!product) throw new NotFoundException('Product not found');

    // Verified-purchase gate: a delivered order item for this product+user
    const purchased = await this.findDeliveredItem(userId, productId);
    if (!purchased) {
      throw new ForbiddenException(
        'You can only review products you have purchased and received',
      );
    }

    const existing = await this.reviewRepo.findOne({
      where: { productId, userId },
    });
    if (existing) {
      throw new ConflictException('You have already reviewed this product');
    }

    const review = this.reviewRepo.create({
      productId,
      userId,
      orderItemId: purchased.id,
      rating: dto.rating,
      title: dto.title,
      comment: dto.comment,
      images: dto.images ?? [],
      isVerifiedPurchase: true,
      status: ReviewStatus.VISIBLE,
    });
    const saved = await this.reviewRepo.save(review);
    await this.recomputeAggregate(productId);
    return saved;
  }

  async update(
    userId: string,
    reviewId: string,
    dto: UpdateReviewDto,
  ): Promise<Review> {
    const review = await this.reviewRepo.findOne({ where: { id: reviewId } });
    if (!review) throw new NotFoundException('Review not found');
    if (review.userId !== userId) throw new ForbiddenException('Not your review');

    if (dto.rating !== undefined) review.rating = dto.rating;
    if (dto.title !== undefined) review.title = dto.title;
    if (dto.comment !== undefined) review.comment = dto.comment;
    if (dto.images !== undefined) review.images = dto.images;
    const saved = await this.reviewRepo.save(review);
    await this.recomputeAggregate(review.productId);
    return saved;
  }

  async remove(
    userId: string,
    role: UserRole,
    reviewId: string,
  ): Promise<void> {
    const review = await this.reviewRepo.findOne({ where: { id: reviewId } });
    if (!review) throw new NotFoundException('Review not found');
    if (role !== UserRole.ADMIN && review.userId !== userId) {
      throw new ForbiddenException('Not your review');
    }
    await this.reviewRepo.remove(review);
    await this.recomputeAggregate(review.productId);
  }

  // -------- Read --------

  async list(productId: string, query: PaginationQueryDto) {
    const [items, total] = await this.reviewRepo.findAndCount({
      where: { productId, status: ReviewStatus.VISIBLE },
      order: { helpfulCount: 'DESC', createdAt: 'DESC' },
      skip: query.offset,
      take: query.limit,
    });
    return paginate(items, total, query.page, query.limit, 'Reviews fetched');
  }

  /** Star-by-star breakdown plus average for a product. */
  async summary(productId: string) {
    const rows = await this.reviewRepo
      .createQueryBuilder('r')
      .select('r.rating', 'rating')
      .addSelect('COUNT(*)', 'count')
      .where('r.productId = :productId AND r.status = :s', {
        productId,
        s: ReviewStatus.VISIBLE,
      })
      .groupBy('r.rating')
      .getRawMany();

    const breakdown: Record<number, number> = { 1: 0, 2: 0, 3: 0, 4: 0, 5: 0 };
    let total = 0;
    let weighted = 0;
    for (const row of rows) {
      const star = Number(row.rating);
      const count = Number(row.count);
      breakdown[star] = count;
      total += count;
      weighted += star * count;
    }
    return {
      average: total ? Number((weighted / total).toFixed(2)) : 0,
      total,
      breakdown,
    };
  }

  // -------- Engagement --------

  async markHelpful(userId: string, reviewId: string): Promise<Review> {
    const review = await this.reviewRepo.findOne({ where: { id: reviewId } });
    if (!review) throw new NotFoundException('Review not found');

    return this.dataSource.transaction(async (manager) => {
      const already = await manager.findOne(ReviewVote, {
        where: { reviewId, userId },
      });
      if (already) {
        throw new ConflictException('You already marked this review helpful');
      }
      await manager.save(manager.create(ReviewVote, { reviewId, userId }));
      await manager.increment(Review, { id: reviewId }, 'helpfulCount', 1);
      return manager.findOneOrFail(Review, { where: { id: reviewId } });
    });
  }

  async respond(
    sellerId: string,
    role: UserRole,
    reviewId: string,
    text: string,
  ): Promise<Review> {
    const review = await this.reviewRepo.findOne({
      where: { id: reviewId },
      relations: ['product'],
    });
    if (!review) throw new NotFoundException('Review not found');
    if (role !== UserRole.ADMIN && review.product.sellerId !== sellerId) {
      throw new ForbiddenException('You can only respond to reviews on your products');
    }
    review.sellerResponse = text;
    review.sellerRespondedAt = new Date();
    return this.reviewRepo.save(review);
  }

  // -------- helpers --------

  private async findDeliveredItem(
    userId: string,
    productId: string,
  ): Promise<OrderItem | null> {
    return this.itemRepo
      .createQueryBuilder('item')
      .innerJoin('item.order', 'order')
      .where('order.userId = :userId', { userId })
      .andWhere('item.productId = :productId', { productId })
      .andWhere('item.status IN (:...statuses)', {
        statuses: [OrderItemStatus.DELIVERED, OrderItemStatus.RETURNED],
      })
      .getOne();
  }

  /** Recomputes a product's avgRating + reviewCount and re-indexes it. */
  private async recomputeAggregate(productId: string): Promise<void> {
    const raw = await this.reviewRepo
      .createQueryBuilder('r')
      .select('AVG(r.rating)', 'avg')
      .addSelect('COUNT(*)', 'count')
      .where('r.productId = :productId AND r.status = :s', {
        productId,
        s: ReviewStatus.VISIBLE,
      })
      .getRawOne<{ avg: string | null; count: string }>();

    const avg = raw?.avg ? Number(Number(raw.avg).toFixed(2)) : 0;
    const count = Number(raw?.count ?? 0);
    await this.productRepo.update(productId, {
      avgRating: avg,
      reviewCount: count,
    });

    // Keep the search index fresh for active products
    const product = await this.productRepo.findOne({ where: { id: productId } });
    if (product?.status === ProductStatus.ACTIVE) {
      this.events.emit(ProductEvents.PUBLISHED, { productId });
    }
  }
}
