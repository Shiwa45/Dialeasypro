import { Entity, Column, Index, ManyToOne, JoinColumn } from 'typeorm';
import { BaseEntity } from '../../../common/entities/base.entity';
import { Product } from '../../catalog/entities/product.entity';

export enum ReviewStatus {
  VISIBLE = 'visible',
  HIDDEN = 'hidden', // moderated out
}

/**
 * A product review by a verified buyer. One review per (product, user),
 * enforced by a unique index. Linked to the order item that proves the
 * purchase.
 */
@Entity('reviews')
@Index(['productId', 'userId'], { unique: true })
export class Review extends BaseEntity {
  @Index()
  @ManyToOne(() => Product, { onDelete: 'CASCADE', nullable: false })
  @JoinColumn({ name: 'productId' })
  product: Product;

  @Column({ type: 'uuid' })
  productId: string;

  @Index()
  @Column({ type: 'uuid' })
  userId: string;

  // The delivered order item that proves the purchase
  @Column({ type: 'uuid', nullable: true })
  orderItemId?: string;

  @Column({ type: 'smallint' })
  rating: number; // 1..5

  @Column({ type: 'varchar', length: 150, nullable: true })
  title?: string;

  @Column({ type: 'varchar', length: 2000, nullable: true })
  comment?: string;

  @Column({ type: 'jsonb', default: () => "'[]'" })
  images: string[];

  @Column({ type: 'boolean', default: true })
  isVerifiedPurchase: boolean;

  @Column({ type: 'int', default: 0 })
  helpfulCount: number;

  // Seller's public response to the review
  @Column({ type: 'varchar', length: 2000, nullable: true })
  sellerResponse?: string;

  @Column({ type: 'timestamptz', nullable: true })
  sellerRespondedAt?: Date;

  @Index()
  @Column({ type: 'enum', enum: ReviewStatus, default: ReviewStatus.VISIBLE })
  status: ReviewStatus;
}
