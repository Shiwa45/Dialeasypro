import { Entity, Column, Index, ManyToOne, JoinColumn } from 'typeorm';
import { BaseEntity } from '../../../common/entities/base.entity';
import { Product } from './product.entity';

/**
 * A buyable variant of a product (e.g. "Black / 256GB").
 * Price, stock, and images live at the variant level so a single
 * product page can offer multiple options. Stock is the source of
 * truth in Postgres; Redis mirrors hot counters for flash sales.
 */
@Entity('product_variants')
export class ProductVariant extends BaseEntity {
  @Index()
  @ManyToOne(() => Product, (p) => p.variants, {
    onDelete: 'CASCADE',
    nullable: false,
  })
  @JoinColumn({ name: 'productId' })
  product: Product;

  @Column({ type: 'uuid' })
  productId: string;

  // Seller's stock-keeping unit (unique per seller)
  @Index({ unique: true })
  @Column({ type: 'varchar', length: 100, unique: true })
  sku: string;

  // Variant attributes e.g. { "Color": "Black", "Storage": "256GB" }
  @Column({ type: 'jsonb', default: () => "'{}'" })
  attributes: Record<string, string>;

  // Prices in paise (integer) to avoid floating-point money bugs
  @Column({ type: 'int' })
  mrp: number; // strike-through price

  @Column({ type: 'int' })
  sellingPrice: number; // actual price

  @Column({ type: 'int', default: 0 })
  stockQuantity: number;

  // Low-stock alert threshold for the seller
  @Column({ type: 'int', default: 5 })
  lowStockThreshold: number;

  @Column({ type: 'jsonb', default: () => "'[]'" })
  imageUrls: string[];

  @Column({ type: 'int', nullable: true })
  weightGrams?: number;

  @Index()
  @Column({ type: 'boolean', default: true })
  isActive: boolean;

  /** Convenience: discount percentage off MRP. */
  get discountPercent(): number {
    if (!this.mrp || this.mrp <= 0) return 0;
    return Math.round(((this.mrp - this.sellingPrice) / this.mrp) * 100);
  }
}
