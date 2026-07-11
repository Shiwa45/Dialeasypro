import { Injectable } from '@nestjs/common';
import { InjectRepository } from '@nestjs/typeorm';
import { Repository } from 'typeorm';
import {
  OrderItem,
  OrderItemStatus,
} from '../../orders/entities/order-item.entity';
import { Review, ReviewStatus } from '../../reviews/entities/review.entity';
import { Return, ReturnStatus } from '../../returns/entities/return.entity';

const DELIVERED = OrderItemStatus.DELIVERED;
const IN_FLIGHT = [
  OrderItemStatus.PLACED,
  OrderItemStatus.CONFIRMED,
  OrderItemStatus.PACKED,
  OrderItemStatus.SHIPPED,
  OrderItemStatus.OUT_FOR_DELIVERY,
];
const PENDING_FULFILLMENT = [
  OrderItemStatus.PLACED,
  OrderItemStatus.CONFIRMED,
  OrderItemStatus.PACKED,
];

/**
 * Read-only analytics for a seller, aggregated from order items, reviews,
 * and returns. All money is paise. Every query is scoped to the seller.
 */
@Injectable()
export class SellerDashboardService {
  constructor(
    @InjectRepository(OrderItem)
    private readonly itemRepo: Repository<OrderItem>,
    @InjectRepository(Review)
    private readonly reviewRepo: Repository<Review>,
    @InjectRepository(Return)
    private readonly returnRepo: Repository<Return>,
  ) {}

  /** Headline KPIs. */
  async overview(sellerId: string) {
    const base = () =>
      this.itemRepo
        .createQueryBuilder('i')
        .where('i.sellerId = :sellerId', { sellerId });

    const earned = await base()
      .andWhere('i.status = :s', { s: DELIVERED })
      .select('COALESCE(SUM(i.lineTotal),0)', 'revenue')
      .addSelect('COALESCE(SUM(i.quantity),0)', 'units')
      .getRawOne<{ revenue: string; units: string }>();

    const pending = await base()
      .andWhere('i.status IN (:...st)', { st: IN_FLIGHT })
      .select('COALESCE(SUM(i.lineTotal),0)', 'revenue')
      .getRawOne<{ revenue: string }>();

    const totalOrders = await base()
      .select('COUNT(DISTINCT i.orderId)', 'c')
      .getRawOne<{ c: string }>();

    const toFulfill = await base()
      .andWhere('i.status IN (:...st)', { st: PENDING_FULFILLMENT })
      .select('COUNT(*)', 'c')
      .getRawOne<{ c: string }>();

    const rating = await this.reviewRepo
      .createQueryBuilder('r')
      .innerJoin('products', 'p', 'p.id = r.productId')
      .where('p.sellerId = :sellerId', { sellerId })
      .andWhere('r.status = :v', { v: ReviewStatus.VISIBLE })
      .select('COALESCE(ROUND(AVG(r.rating)::numeric,2),0)', 'avg')
      .addSelect('COUNT(*)', 'count')
      .getRawOne<{ avg: string; count: string }>();

    const deliveredCount = Number(earned?.units ?? 0);
    const returnsCount = await this.returnRepo.count({
      where: { sellerId },
    });

    return {
      earnedRevenue: Number(earned?.revenue ?? 0),
      pendingRevenue: Number(pending?.revenue ?? 0),
      totalOrders: Number(totalOrders?.c ?? 0),
      unitsSold: deliveredCount,
      pendingFulfillment: Number(toFulfill?.c ?? 0),
      averageRating: Number(rating?.avg ?? 0),
      reviewCount: Number(rating?.count ?? 0),
      returnsCount,
    };
  }

  /** Sales trend bucketed by day (7d/30d) or month (12m). */
  async salesTrend(sellerId: string, period: '7d' | '30d' | '12m') {
    const isMonthly = period === '12m';
    const interval =
      period === '7d' ? '7 days' : period === '30d' ? '30 days' : '12 months';
    const bucket = isMonthly ? 'month' : 'day';

    const rows = await this.itemRepo
      .createQueryBuilder('i')
      .where('i.sellerId = :sellerId', { sellerId })
      .andWhere('i.status = :s', { s: DELIVERED })
      .andWhere(`i.createdAt >= NOW() - INTERVAL '${interval}'`)
      .select(`date_trunc('${bucket}', i.createdAt)`, 'bucket')
      .addSelect('SUM(i.lineTotal)', 'revenue')
      .addSelect('COUNT(DISTINCT i.orderId)', 'orders')
      .addSelect('SUM(i.quantity)', 'units')
      .groupBy('bucket')
      .orderBy('bucket', 'ASC')
      .getRawMany();

    return rows.map((r) => ({
      period: r.bucket,
      revenue: Number(r.revenue),
      orders: Number(r.orders),
      units: Number(r.units),
    }));
  }

  /** Item counts and value grouped by fulfillment status. */
  async ordersByStatus(sellerId: string) {
    const rows = await this.itemRepo
      .createQueryBuilder('i')
      .where('i.sellerId = :sellerId', { sellerId })
      .select('i.status', 'status')
      .addSelect('COUNT(*)', 'count')
      .addSelect('COALESCE(SUM(i.lineTotal),0)', 'value')
      .groupBy('i.status')
      .getRawMany();
    return rows.map((r) => ({
      status: r.status,
      count: Number(r.count),
      value: Number(r.value),
    }));
  }

  /** Best-selling products by revenue. */
  async topProducts(sellerId: string, limit: number) {
    const rows = await this.itemRepo
      .createQueryBuilder('i')
      .where('i.sellerId = :sellerId', { sellerId })
      .andWhere('i.status = :s', { s: DELIVERED })
      .select('i.productId', 'productId')
      .addSelect('MAX(i.productTitle)', 'title')
      .addSelect('SUM(i.quantity)', 'units')
      .addSelect('SUM(i.lineTotal)', 'revenue')
      .groupBy('i.productId')
      .orderBy('revenue', 'DESC')
      .limit(limit)
      .getRawMany();
    return rows.map((r) => ({
      productId: r.productId,
      title: r.title,
      units: Number(r.units),
      revenue: Number(r.revenue),
    }));
  }

  /** Return analytics: totals, by status, by reason, and rate. */
  async returns(sellerId: string) {
    const byStatus = await this.returnRepo
      .createQueryBuilder('r')
      .where('r.sellerId = :sellerId', { sellerId })
      .select('r.status', 'status')
      .addSelect('COUNT(*)', 'count')
      .groupBy('r.status')
      .getRawMany();

    const byReason = await this.returnRepo
      .createQueryBuilder('r')
      .where('r.sellerId = :sellerId', { sellerId })
      .select('r.reason', 'reason')
      .addSelect('COUNT(*)', 'count')
      .groupBy('r.reason')
      .getRawMany();

    const refunded = await this.returnRepo
      .createQueryBuilder('r')
      .where('r.sellerId = :sellerId AND r.status = :s', {
        sellerId,
        s: ReturnStatus.REFUNDED,
      })
      .select('COALESCE(SUM(r.refundAmount),0)', 'total')
      .getRawOne<{ total: string }>();

    const deliveredUnits = await this.itemRepo
      .createQueryBuilder('i')
      .where('i.sellerId = :sellerId AND i.status IN (:...s)', {
        sellerId,
        s: [DELIVERED, OrderItemStatus.RETURNED],
      })
      .select('COALESCE(SUM(i.quantity),0)', 'u')
      .getRawOne<{ u: string }>();

    const totalReturns = byStatus.reduce(
      (sum, r) => sum + Number(r.count),
      0,
    );
    const delivered = Number(deliveredUnits?.u ?? 0);
    return {
      totalReturns,
      refundedAmount: Number(refunded?.total ?? 0),
      returnRate: delivered ? Number(((totalReturns / delivered) * 100).toFixed(2)) : 0,
      byStatus: byStatus.map((r) => ({ status: r.status, count: Number(r.count) })),
      byReason: byReason.map((r) => ({ reason: r.reason, count: Number(r.count) })),
    };
  }

  /**
   * Settlement summary: gross delivered sales minus platform commission
   * (per-category rate) and refunds = net payable to the seller.
   */
  async settlement(sellerId: string) {
    const gross = await this.itemRepo
      .createQueryBuilder('i')
      .where('i.sellerId = :sellerId AND i.status = :s', {
        sellerId,
        s: DELIVERED,
      })
      .select('COALESCE(SUM(i.lineTotal),0)', 'gross')
      .getRawOne<{ gross: string }>();

    // Commission via category rate (order_items → products → categories)
    const commissionRow = await this.itemRepo
      .createQueryBuilder('i')
      .innerJoin('products', 'p', 'p.id = i.productId')
      .innerJoin('categories', 'c', 'c.id = p.categoryId')
      .where('i.sellerId = :sellerId AND i.status = :s', {
        sellerId,
        s: DELIVERED,
      })
      .select(
        'COALESCE(SUM(i.lineTotal * c.commissionRate / 100.0),0)',
        'commission',
      )
      .getRawOne<{ commission: string }>();

    const refunds = await this.returnRepo
      .createQueryBuilder('r')
      .where('r.sellerId = :sellerId AND r.status = :s', {
        sellerId,
        s: ReturnStatus.REFUNDED,
      })
      .select('COALESCE(SUM(r.refundAmount),0)', 'refunds')
      .getRawOne<{ refunds: string }>();

    const grossSales = Number(gross?.gross ?? 0);
    const commission = Math.round(Number(commissionRow?.commission ?? 0));
    const refundTotal = Number(refunds?.refunds ?? 0);
    const netPayable = grossSales - commission - refundTotal;

    return {
      grossSales,
      platformCommission: commission,
      refunds: refundTotal,
      netPayable,
    };
  }
}
