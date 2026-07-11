import { Entity, Column, Index } from 'typeorm';
import { BaseEntity } from '../../../common/entities/base.entity';

export enum DiscountType {
  PERCENTAGE = 'percentage',
  FLAT = 'flat',
}

export enum CouponScope {
  ALL = 'all', // whole platform
  CATEGORY = 'category', // items in a category
  SELLER = 'seller', // items from a seller
}

/**
 * A discount coupon. Money fields are paise; percentage values are
 * whole-number percents (10 = 10%). Scope narrows which items count
 * toward the eligible subtotal.
 */
@Entity('coupons')
export class Coupon extends BaseEntity {
  @Index({ unique: true })
  @Column({ type: 'varchar', length: 40, unique: true })
  code: string; // stored uppercased

  @Column({ type: 'varchar', length: 200, nullable: true })
  description?: string;

  @Column({ type: 'enum', enum: DiscountType })
  discountType: DiscountType;

  @Column({ type: 'int' })
  discountValue: number; // percent (10) OR flat paise

  @Column({ type: 'int', nullable: true })
  maxDiscountAmount?: number; // cap for percentage (paise)

  @Column({ type: 'int', default: 0 })
  minCartValue: number; // paise

  @Column({ type: 'enum', enum: CouponScope, default: CouponScope.ALL })
  scope: CouponScope;

  @Column({ type: 'uuid', nullable: true })
  scopeId?: string; // categoryId or sellerId when scoped

  @Column({ type: 'int', nullable: true })
  usageLimit?: number; // global cap (null = unlimited)

  @Column({ type: 'int', default: 1 })
  perUserLimit: number;

  @Column({ type: 'int', default: 0 })
  usedCount: number;

  @Column({ type: 'timestamptz' })
  validFrom: Date;

  @Column({ type: 'timestamptz' })
  validUntil: Date;

  @Index()
  @Column({ type: 'boolean', default: true })
  isActive: boolean;

  // Seller who owns a seller-scoped coupon (for authorization)
  @Column({ type: 'uuid', nullable: true })
  createdBySeller?: string;
}
