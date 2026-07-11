import { Entity, Column, Index, ManyToOne, JoinColumn } from 'typeorm';
import { BaseEntity } from '../../../common/entities/base.entity';
import { Coupon } from './coupon.entity';

/**
 * Records each successful coupon use, enforcing per-user limits and
 * giving an audit trail of discounts granted.
 */
@Entity('coupon_redemptions')
@Index(['couponId', 'userId'])
export class CouponRedemption extends BaseEntity {
  @ManyToOne(() => Coupon, { onDelete: 'CASCADE', nullable: false })
  @JoinColumn({ name: 'couponId' })
  coupon: Coupon;

  @Column({ type: 'uuid' })
  couponId: string;

  @Index()
  @Column({ type: 'uuid' })
  userId: string;

  @Index()
  @Column({ type: 'uuid' })
  orderId: string;

  @Column({ type: 'int' })
  discountAmount: number; // paise
}
