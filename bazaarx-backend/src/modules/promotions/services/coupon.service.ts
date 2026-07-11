import {
  Injectable,
  NotFoundException,
  ForbiddenException,
  BadRequestException,
  ConflictException,
} from '@nestjs/common';
import { InjectRepository } from '@nestjs/typeorm';
import { EntityManager, In, Repository } from 'typeorm';
import { Coupon, CouponScope, DiscountType } from '../entities/coupon.entity';
import { CouponRedemption } from '../entities/coupon-redemption.entity';
import { Product } from '../../catalog/entities/product.entity';
import { CreateCouponDto } from '../dto/coupon.dto';
import { UserRole } from '../../users/entities/user.entity';

/** A cart line as seen by coupon logic. */
export interface CouponCartLine {
  productId: string;
  lineTotal: number;
}

export interface CouponResult {
  coupon: Coupon;
  discount: number; // paise
  eligibleSubtotal: number;
}

@Injectable()
export class CouponService {
  constructor(
    @InjectRepository(Coupon)
    private readonly couponRepo: Repository<Coupon>,
    @InjectRepository(CouponRedemption)
    private readonly redemptionRepo: Repository<CouponRedemption>,
    @InjectRepository(Product)
    private readonly productRepo: Repository<Product>,
  ) {}

  // -------- Management --------

  async create(
    actorId: string,
    role: UserRole,
    dto: CreateCouponDto,
  ): Promise<Coupon> {
    const code = dto.code.trim().toUpperCase();
    const exists = await this.couponRepo.findOne({ where: { code } });
    if (exists) throw new ConflictException('Coupon code already exists');

    // Sellers may only create coupons scoped to themselves
    let scope = dto.scope ?? CouponScope.ALL;
    let scopeId = dto.scopeId;
    let createdBySeller: string | undefined;
    if (role === UserRole.SELLER) {
      scope = CouponScope.SELLER;
      scopeId = actorId;
      createdBySeller = actorId;
    }
    if (scope !== CouponScope.ALL && !scopeId) {
      throw new BadRequestException('scopeId is required for scoped coupons');
    }
    if (
      dto.discountType === DiscountType.PERCENTAGE &&
      dto.discountValue > 100
    ) {
      throw new BadRequestException('Percentage discount cannot exceed 100');
    }

    const coupon = this.couponRepo.create({
      code,
      description: dto.description,
      discountType: dto.discountType,
      discountValue: dto.discountValue,
      maxDiscountAmount: dto.maxDiscountAmount,
      minCartValue: dto.minCartValue ?? 0,
      scope,
      scopeId,
      usageLimit: dto.usageLimit,
      perUserLimit: dto.perUserLimit ?? 1,
      validFrom: new Date(dto.validFrom),
      validUntil: new Date(dto.validUntil),
      createdBySeller,
    });
    return this.couponRepo.save(coupon);
  }

  async listAll(): Promise<Coupon[]> {
    return this.couponRepo.find({ order: { createdAt: 'DESC' } });
  }

  async listActivePublic(): Promise<Coupon[]> {
    const now = new Date();
    return this.couponRepo
      .createQueryBuilder('c')
      .where('c.isActive = true')
      .andWhere('c.validFrom <= :now AND c.validUntil >= :now', { now })
      .andWhere('c.scope = :scope', { scope: CouponScope.ALL })
      .orderBy('c.createdAt', 'DESC')
      .getMany();
  }

  async deactivate(
    actorId: string,
    role: UserRole,
    id: string,
  ): Promise<Coupon> {
    const coupon = await this.couponRepo.findOne({ where: { id } });
    if (!coupon) throw new NotFoundException('Coupon not found');
    if (role === UserRole.SELLER && coupon.createdBySeller !== actorId) {
      throw new ForbiddenException('Not your coupon');
    }
    coupon.isActive = false;
    return this.couponRepo.save(coupon);
  }

  // -------- Validation & discount --------

  /**
   * Validates a coupon for a user + cart and returns the discount.
   * Throws a BadRequest with a clear reason when not applicable.
   */
  async validateAndCompute(
    code: string,
    userId: string,
    lines: CouponCartLine[],
  ): Promise<CouponResult> {
    const coupon = await this.couponRepo.findOne({
      where: { code: code.trim().toUpperCase() },
    });
    if (!coupon || !coupon.isActive) {
      throw new BadRequestException('Invalid or inactive coupon');
    }

    const now = Date.now();
    if (now < coupon.validFrom.getTime()) {
      throw new BadRequestException('Coupon is not yet active');
    }
    if (now > coupon.validUntil.getTime()) {
      throw new BadRequestException('Coupon has expired');
    }
    if (
      coupon.usageLimit != null &&
      coupon.usedCount >= coupon.usageLimit
    ) {
      throw new BadRequestException('Coupon usage limit reached');
    }

    const usedByUser = await this.redemptionRepo.count({
      where: { couponId: coupon.id, userId },
    });
    if (usedByUser >= coupon.perUserLimit) {
      throw new BadRequestException(
        'You have already used this coupon the maximum number of times',
      );
    }

    const eligibleSubtotal = await this.eligibleSubtotal(coupon, lines);
    if (eligibleSubtotal <= 0) {
      throw new BadRequestException(
        'No eligible items in your cart for this coupon',
      );
    }
    if (eligibleSubtotal < coupon.minCartValue) {
      const short = (coupon.minCartValue - eligibleSubtotal) / 100;
      throw new BadRequestException(
        `Add items worth ₹${short.toFixed(2)} more to use this coupon`,
      );
    }

    const discount = this.computeDiscount(coupon, eligibleSubtotal);
    return { coupon, discount, eligibleSubtotal };
  }

  /** Records a redemption and bumps the global counter (transactional). */
  async redeem(
    manager: EntityManager,
    coupon: Coupon,
    userId: string,
    orderId: string,
    discount: number,
  ): Promise<void> {
    await manager.increment(Coupon, { id: coupon.id }, 'usedCount', 1);
    await manager.save(
      manager.create(CouponRedemption, {
        couponId: coupon.id,
        userId,
        orderId,
        discountAmount: discount,
      }),
    );
  }

  // -------- helpers --------

  private computeDiscount(coupon: Coupon, eligibleSubtotal: number): number {
    let discount: number;
    if (coupon.discountType === DiscountType.PERCENTAGE) {
      discount = Math.floor((eligibleSubtotal * coupon.discountValue) / 100);
      if (coupon.maxDiscountAmount != null) {
        discount = Math.min(discount, coupon.maxDiscountAmount);
      }
    } else {
      discount = coupon.discountValue;
    }
    // Never discount more than the eligible items are worth
    return Math.min(discount, eligibleSubtotal);
  }

  /** Sum of line totals that the coupon's scope applies to. */
  private async eligibleSubtotal(
    coupon: Coupon,
    lines: CouponCartLine[],
  ): Promise<number> {
    if (coupon.scope === CouponScope.ALL) {
      return lines.reduce((s, l) => s + l.lineTotal, 0);
    }
    const productIds = [...new Set(lines.map((l) => l.productId))];
    const products = await this.productRepo.find({
      where: { id: In(productIds) },
    });
    const match = new Map(products.map((p) => [p.id, p]));
    return lines.reduce((sum, l) => {
      const p = match.get(l.productId);
      if (!p) return sum;
      const ok =
        coupon.scope === CouponScope.CATEGORY
          ? p.categoryId === coupon.scopeId
          : p.sellerId === coupon.scopeId;
      return ok ? sum + l.lineTotal : sum;
    }, 0);
  }
}
