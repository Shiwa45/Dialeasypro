import {
  Entity,
  Column,
  Index,
  ManyToOne,
  OneToMany,
  JoinColumn,
} from 'typeorm';
import { BaseEntity } from '../../../common/entities/base.entity';
import { User } from '../../users/entities/user.entity';
import { Category } from './category.entity';
import { Brand } from './brand.entity';
import { ProductVariant } from './product-variant.entity';

/**
 * Listing lifecycle. Products are not visible to buyers until a seller
 * publishes and (optionally) an admin approves — protecting catalogue
 * quality and enabling moderation.
 */
export enum ProductStatus {
  DRAFT = 'draft', // seller still editing
  PENDING_REVIEW = 'pending_review', // submitted, awaiting admin
  ACTIVE = 'active', // live, buyable
  REJECTED = 'rejected', // admin rejected
  INACTIVE = 'inactive', // seller hid it / out of stock
}

@Entity('products')
@Index(['status', 'categoryId']) // common browse query
export class Product extends BaseEntity {
  // The seller (a user with role=seller) who owns this listing
  @Index()
  @ManyToOne(() => User, { onDelete: 'CASCADE', nullable: false })
  @JoinColumn({ name: 'sellerId' })
  seller: User;

  @Column({ type: 'uuid' })
  sellerId: string;

  @Index()
  @ManyToOne(() => Category, { nullable: false, onDelete: 'RESTRICT' })
  @JoinColumn({ name: 'categoryId' })
  category: Category;

  @Column({ type: 'uuid' })
  categoryId: string;

  @ManyToOne(() => Brand, { nullable: true, onDelete: 'SET NULL' })
  @JoinColumn({ name: 'brandId' })
  brand?: Brand;

  @Index()
  @Column({ type: 'uuid', nullable: true })
  brandId?: string;

  @Column({ type: 'varchar', length: 300 })
  title: string;

  // HSN/SAC code for GST classification (8-digit max)
  @Column({ type: 'varchar', length: 8, default: '9999' })
  hsnCode: string;

  @Index({ unique: true })
  @Column({ type: 'varchar', length: 350, unique: true })
  slug: string;

  @Column({ type: 'text', nullable: true })
  description?: string;

  // Up to 5 short bullet highlights
  @Column({ type: 'jsonb', default: () => "'[]'" })
  highlights: string[];

  // Structured, category-specific specs e.g. { "RAM": "8GB", "Color": "Black" }
  @Column({ type: 'jsonb', default: () => "'{}'" })
  specifications: Record<string, string>;

  // Internal search tags
  @Column({ type: 'jsonb', default: () => "'[]'" })
  tags: string[];

  @Index()
  @Column({ type: 'enum', enum: ProductStatus, default: ProductStatus.DRAFT })
  status: ProductStatus;

  @Column({ type: 'varchar', length: 500, nullable: true })
  rejectionReason?: string;

  // Aggregates kept in sync by the reviews module (denormalized for speed)
  @Column({ type: 'decimal', precision: 3, scale: 2, default: 0 })
  avgRating: number;

  @Column({ type: 'int', default: 0 })
  reviewCount: number;

  @OneToMany(() => ProductVariant, (v) => v.product, { cascade: true })
  variants: ProductVariant[];

  // SEO
  @Column({ type: 'varchar', length: 255, nullable: true })
  metaTitle?: string;

  @Column({ type: 'varchar', length: 500, nullable: true })
  metaDescription?: string;
}
