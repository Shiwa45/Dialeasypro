import { Inject, Injectable } from '@nestjs/common';
import { InjectRepository } from '@nestjs/typeorm';
import { In, Repository } from 'typeorm';
import Redis from 'ioredis';
import { REDIS_CLIENT } from '../../../database/redis.module';
import { Product, ProductStatus } from '../../catalog/entities/product.entity';
import { OrderItem, OrderItemStatus } from '../../orders/entities/order-item.entity';

export interface ProductCard {
  id: string;
  title: string;
  slug: string;
  minPrice: number;
  avgRating: number;
  reviewCount: number;
  imageUrl: string | null;
}

const VIEWED_LIMIT = 20;

/**
 * Recommendations derived from the catalogue and real purchase data.
 * No ML service — these are explainable, query-driven heuristics that
 * work from day one and improve as order data accumulates.
 */
@Injectable()
export class RecommendationService {
  constructor(
    @InjectRepository(Product)
    private readonly productRepo: Repository<Product>,
    @InjectRepository(OrderItem)
    private readonly itemRepo: Repository<OrderItem>,
    @Inject(REDIS_CLIENT) private readonly redis: Redis,
  ) {}

  /** Other active products in the same category, best-rated first. */
  async related(productId: string, limit: number): Promise<ProductCard[]> {
    const product = await this.productRepo.findOne({ where: { id: productId } });
    if (!product) return [];
    const products = await this.productRepo.find({
      where: {
        categoryId: product.categoryId,
        status: ProductStatus.ACTIVE,
      },
      relations: ['variants'],
      order: { avgRating: 'DESC', reviewCount: 'DESC' },
      take: limit + 1,
    });
    return this.toCards(products.filter((p) => p.id !== productId).slice(0, limit));
  }

  /** Products that co-occur in orders containing this product. */
  async frequentlyBoughtTogether(
    productId: string,
    limit: number,
  ): Promise<ProductCard[]> {
    const rows = await this.itemRepo
      .createQueryBuilder('oi1')
      .innerJoin(
        OrderItem,
        'oi2',
        'oi2.orderId = oi1.orderId AND oi2.productId != oi1.productId',
      )
      .where('oi1.productId = :productId', { productId })
      .select('oi2.productId', 'productId')
      .addSelect('COUNT(*)', 'cnt')
      .groupBy('oi2.productId')
      .orderBy('cnt', 'DESC')
      .limit(limit)
      .getRawMany();

    const ids = rows.map((r) => r.productId);
    return this.loadActiveCards(ids);
  }

  /** "For you": active products in categories the user has bought from. */
  async forYou(userId: string, limit: number): Promise<ProductCard[]> {
    // Categories the user has purchased in + products already bought
    const purchased = await this.itemRepo
      .createQueryBuilder('i')
      .innerJoin('products', 'p', 'p.id = i.productId')
      .innerJoin('orders', 'o', 'o.id = i.orderId')
      .where('o.userId = :userId', { userId })
      .select('DISTINCT p.categoryId', 'categoryId')
      .getRawMany();

    const categoryIds = purchased.map((r) => r.categoryId).filter(Boolean);
    if (categoryIds.length === 0) {
      // Cold start → fall back to trending
      return this.trending(limit);
    }

    const boughtRows = await this.itemRepo
      .createQueryBuilder('i')
      .innerJoin('orders', 'o', 'o.id = i.orderId')
      .where('o.userId = :userId', { userId })
      .select('DISTINCT i.productId', 'productId')
      .getRawMany();
    const boughtIds = new Set(boughtRows.map((r) => r.productId));

    const products = await this.productRepo.find({
      where: {
        categoryId: In(categoryIds),
        status: ProductStatus.ACTIVE,
      },
      relations: ['variants'],
      order: { avgRating: 'DESC', reviewCount: 'DESC' },
      take: limit + boughtIds.size,
    });
    return this.toCards(
      products.filter((p) => !boughtIds.has(p.id)).slice(0, limit),
    );
  }

  /** Trending: most units sold (delivered) in the last 30 days. */
  async trending(limit: number): Promise<ProductCard[]> {
    const rows = await this.itemRepo
      .createQueryBuilder('i')
      .where('i.status = :s', { s: OrderItemStatus.DELIVERED })
      .andWhere("i.createdAt >= NOW() - INTERVAL '30 days'")
      .select('i.productId', 'productId')
      .addSelect('SUM(i.quantity)', 'units')
      .groupBy('i.productId')
      .orderBy('units', 'DESC')
      .limit(limit)
      .getRawMany();

    const ids = rows.map((r) => r.productId);
    if (ids.length === 0) {
      // No sales yet → newest active products
      const newest = await this.productRepo.find({
        where: { status: ProductStatus.ACTIVE },
        relations: ['variants'],
        order: { createdAt: 'DESC' },
        take: limit,
      });
      return this.toCards(newest);
    }
    return this.loadActiveCards(ids);
  }

  // -------- Recently viewed (Redis) --------

  async trackView(userId: string, productId: string): Promise<void> {
    const key = `viewed:${userId}`;
    await this.redis.lrem(key, 0, productId); // de-dupe
    await this.redis.lpush(key, productId);
    await this.redis.ltrim(key, 0, VIEWED_LIMIT - 1);
    await this.redis.expire(key, 30 * 24 * 60 * 60);
  }

  async recentlyViewed(userId: string, limit: number): Promise<ProductCard[]> {
    const ids = await this.redis.lrange(`viewed:${userId}`, 0, limit - 1);
    if (ids.length === 0) return [];
    const cards = await this.loadActiveCards(ids);
    // preserve recency order
    const order = new Map(ids.map((id, i) => [id, i]));
    return cards.sort((a, b) => (order.get(a.id)! - order.get(b.id)!));
  }

  // -------- helpers --------

  private async loadActiveCards(ids: string[]): Promise<ProductCard[]> {
    if (ids.length === 0) return [];
    const products = await this.productRepo.find({
      where: { id: In(ids), status: ProductStatus.ACTIVE },
      relations: ['variants'],
    });
    // preserve input order (co-purchase / recency ranking)
    const rank = new Map(ids.map((id, i) => [id, i]));
    return this.toCards(
      products.sort((a, b) => (rank.get(a.id)! - rank.get(b.id)!)),
    );
  }

  private toCards(products: Product[]): ProductCard[] {
    return products.map((p) => {
      const prices = (p.variants ?? [])
        .filter((v) => v.isActive)
        .map((v) => v.sellingPrice);
      return {
        id: p.id,
        title: p.title,
        slug: p.slug,
        minPrice: prices.length ? Math.min(...prices) : 0,
        avgRating: Number(p.avgRating),
        reviewCount: p.reviewCount,
        imageUrl: (p.variants ?? [])[0]?.imageUrls?.[0] ?? null,
      };
    });
  }
}
