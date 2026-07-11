import { Entity, Column, Index } from 'typeorm';
import { BaseEntity } from '../../../common/entities/base.entity';

/**
 * Product brand. A lightweight registry so listings can be grouped
 * into brand stores and filtered by brand in search.
 */
@Entity('brands')
export class Brand extends BaseEntity {
  @Column({ type: 'varchar', length: 150 })
  name: string;

  @Index({ unique: true })
  @Column({ type: 'varchar', length: 180, unique: true })
  slug: string;

  @Column({ type: 'varchar', length: 500, nullable: true })
  logoUrl?: string;

  @Column({ type: 'text', nullable: true })
  description?: string;

  @Index()
  @Column({ type: 'boolean', default: true })
  isActive: boolean;
}
