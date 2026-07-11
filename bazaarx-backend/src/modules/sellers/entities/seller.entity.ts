import { Entity, Column, Index, OneToOne, JoinColumn, OneToMany } from 'typeorm';
import { BaseEntity } from '../../../common/entities/base.entity';
import { User } from '../../users/entities/user.entity';
import { SellerDocument } from './seller-document.entity';

export enum BusinessType {
  INDIVIDUAL = 'individual',
  PROPRIETORSHIP = 'proprietorship',
  PARTNERSHIP = 'partnership',
  LLP = 'llp',
  PRIVATE_LIMITED = 'private_limited',
}

export enum SellerStatus {
  PENDING = 'pending', // applied, awaiting admin review
  APPROVED = 'approved', // verified, can list products
  REJECTED = 'rejected', // application rejected
  SUSPENDED = 'suspended', // temporarily blocked by admin
}

/**
 * A seller's business profile. 1:1 with a User. When approved, the
 * linked user's role is promoted to SELLER so they can list products.
 */
@Entity('sellers')
export class Seller extends BaseEntity {
  @Index({ unique: true })
  @OneToOne(() => User, { onDelete: 'CASCADE', nullable: false })
  @JoinColumn({ name: 'userId' })
  user: User;

  @Column({ type: 'uuid', unique: true })
  userId: string;

  // Public-facing store name shown to buyers
  @Column({ type: 'varchar', length: 200 })
  displayName: string;

  // Legal business name
  @Column({ type: 'varchar', length: 200 })
  businessName: string;

  @Column({ type: 'enum', enum: BusinessType })
  businessType: BusinessType;

  @Index({ unique: true })
  @Column({ type: 'varchar', length: 15, unique: true })
  gstin: string;

  @Column({ type: 'varchar', length: 10 })
  pan: string;

  // Bank details for payouts (penny-drop verified later via RazorpayX)
  @Column({ type: 'varchar', length: 150 })
  bankAccountHolder: string;

  @Column({ type: 'varchar', length: 20 })
  bankAccountNumber: string;

  @Column({ type: 'varchar', length: 11 })
  bankIfsc: string;

  @Index()
  @Column({ type: 'enum', enum: SellerStatus, default: SellerStatus.PENDING })
  status: SellerStatus;

  @Column({ type: 'varchar', length: 500, nullable: true })
  rejectionReason?: string;

  // Flipkart-style health metric (0-100); drives perks/penalties later
  @Column({ type: 'decimal', precision: 5, scale: 2, default: 100 })
  accountHealthScore: number;

  // Per-seller commission override (null = use category rate)
  @Column({ type: 'decimal', precision: 5, scale: 2, nullable: true })
  commissionOverride?: number;

  @Column({ type: 'timestamptz', nullable: true })
  approvedAt?: Date;

  @Column({ type: 'uuid', nullable: true })
  approvedByAdminId?: string;

  @OneToMany(() => SellerDocument, (d) => d.seller, { cascade: true })
  documents: SellerDocument[];
}
