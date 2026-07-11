import {
  PrimaryGeneratedColumn,
  CreateDateColumn,
  UpdateDateColumn,
  DeleteDateColumn,
} from 'typeorm';

/**
 * Shared base for all relational entities:
 *  - UUID primary key (safe to expose publicly, non-enumerable)
 *  - automatic created/updated timestamps
 *  - soft-delete column (deletedAt) — rows are never hard-deleted,
 *    which matters for orders, payments, and audit/compliance.
 */
export abstract class BaseEntity {
  @PrimaryGeneratedColumn('uuid')
  id: string;

  @CreateDateColumn({ type: 'timestamptz' })
  createdAt: Date;

  @UpdateDateColumn({ type: 'timestamptz' })
  updatedAt: Date;

  @DeleteDateColumn({ type: 'timestamptz', nullable: true })
  deletedAt?: Date;
}
