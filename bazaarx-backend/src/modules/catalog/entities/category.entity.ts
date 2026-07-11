import { Entity, Column, Index, ManyToOne, OneToMany, JoinColumn } from 'typeorm';
import { BaseEntity } from '../../../common/entities/base.entity';

/**
 * Product category, self-referencing for a 3-level hierarchy:
 *   Category > Subcategory > Sub-subcategory
 *
 * `level` (0,1,2) is denormalized for fast filtering and to enforce
 * the max depth. Commission rate and GST are set per category and
 * inherited by products (overridable later).
 */
@Entity('categories')
export class Category extends BaseEntity {
  @Column({ type: 'varchar', length: 150 })
  name: string;

  @Index({ unique: true })
  @Column({ type: 'varchar', length: 180, unique: true })
  slug: string;

  @ManyToOne(() => Category, (c) => c.children, {
    nullable: true,
    onDelete: 'CASCADE',
  })
  @JoinColumn({ name: 'parentId' })
  parent?: Category;

  @Index()
  @Column({ type: 'uuid', nullable: true })
  parentId?: string;

  @OneToMany(() => Category, (c) => c.parent)
  children: Category[];

  @Column({ type: 'smallint', default: 0 })
  level: number; // 0 = root, max 2

  @Column({ type: 'varchar', length: 500, nullable: true })
  imageUrl?: string;

  @Column({ type: 'varchar', length: 500, nullable: true })
  iconUrl?: string;

  @Index()
  @Column({ type: 'boolean', default: true })
  isActive: boolean;

  @Column({ type: 'int', default: 0 })
  sortOrder: number;

  // Commission % charged to sellers for products in this category
  @Column({ type: 'decimal', precision: 5, scale: 2, default: 5 })
  commissionRate: number;

  // Default GST slab for products here (0,5,12,18,28)
  @Column({ type: 'decimal', precision: 5, scale: 2, default: 18 })
  gstRate: number;

  // SEO
  @Column({ type: 'varchar', length: 255, nullable: true })
  metaTitle?: string;

  @Column({ type: 'varchar', length: 500, nullable: true })
  metaDescription?: string;
}
