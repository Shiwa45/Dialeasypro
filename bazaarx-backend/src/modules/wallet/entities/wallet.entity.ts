import { Entity, Column, Index, ManyToOne, JoinColumn } from 'typeorm';
import { BaseEntity } from '../../../common/entities/base.entity';

/** Store-credit wallet, one per user. Balance in paise. */
@Entity('wallets')
export class Wallet extends BaseEntity {
  @Index({ unique: true })
  @Column({ type: 'uuid', unique: true })
  userId: string;

  @Column({ type: 'bigint', default: 0, transformer: {
    to: (v: number) => v,
    from: (v: string) => parseInt(v, 10),
  } })
  balance: number; // paise
}

export enum WalletTxnType {
  CREDIT = 'credit',
  DEBIT = 'debit',
}

export enum WalletTxnSource {
  TOPUP = 'topup',
  REFUND = 'refund',
  PURCHASE = 'purchase',
  CASHBACK = 'cashback',
  BNPL_REPAYMENT = 'bnpl_repayment',
  REVERSAL = 'reversal',
}

/** Immutable ledger entry for every wallet movement. */
@Entity('wallet_transactions')
export class WalletTransaction extends BaseEntity {
  @Index()
  @ManyToOne(() => Wallet, { onDelete: 'CASCADE', nullable: false })
  @JoinColumn({ name: 'walletId' })
  wallet: Wallet;

  @Column({ type: 'uuid' })
  walletId: string;

  @Column({ type: 'enum', enum: WalletTxnType })
  type: WalletTxnType;

  @Column({ type: 'enum', enum: WalletTxnSource })
  source: WalletTxnSource;

  @Column({ type: 'int' })
  amount: number; // paise (always positive)

  @Column({ type: 'bigint', transformer: {
    to: (v: number) => v,
    from: (v: string) => parseInt(v, 10),
  } })
  balanceAfter: number;

  @Column({ type: 'varchar', length: 200, nullable: true })
  description?: string;

  @Column({ type: 'varchar', length: 100, nullable: true })
  reference?: string; // orderId / gatewayOrderId / returnId
}

/**
 * A simple Buy-Now-Pay-Later credit line per user. `used` rises on BNPL
 * checkout and falls on repayment; available = limit - used.
 */
@Entity('bnpl_accounts')
export class BnplAccount extends BaseEntity {
  @Index({ unique: true })
  @Column({ type: 'uuid', unique: true })
  userId: string;

  @Column({ type: 'int', default: 2000000 }) // ₹20,000 default limit (paise)
  creditLimit: number;

  @Column({ type: 'int', default: 0 })
  used: number;

  @Column({ type: 'boolean', default: true })
  isActive: boolean;
}
