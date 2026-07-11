import { Entity, Column, Index, ManyToOne, OneToMany, JoinColumn } from 'typeorm';
import { BaseEntity } from '../../../common/entities/base.entity';
import { User } from '../../users/entities/user.entity';
import { OrderItem } from './order-item.entity';

export enum PaymentMethod {
  COD = 'cod',
  UPI = 'upi',
  CARD = 'card',
  NETBANKING = 'netbanking',
  WALLET = 'wallet',
  BNPL = 'bnpl',
}

export enum PaymentStatus {
  PENDING = 'pending', // COD: until delivered; online: until paid
  PAID = 'paid',
  FAILED = 'failed',
  REFUNDED = 'refunded',
}

/**
 * Overall order placed by a buyer in one checkout. Items may belong to
 * multiple sellers; each OrderItem carries its own fulfillment status,
 * so sellers ship independently. Money is stored in paise (integers).
 *
 * The delivery address is SNAPSHOTTED as JSON at order time — later
 * edits to the saved address must not change a historical order.
 */
@Entity('orders')
export class Order extends BaseEntity {
  @Index({ unique: true })
  @Column({ type: 'varchar', length: 30, unique: true })
  orderNumber: string; // e.g. ORD-2026-AB12CD34

  @Index()
  @ManyToOne(() => User, { onDelete: 'RESTRICT', nullable: false })
  @JoinColumn({ name: 'userId' })
  user: User;

  @Column({ type: 'uuid' })
  userId: string;

  // Frozen copy of the delivery address
  @Column({ type: 'jsonb' })
  shippingAddress: Record<string, unknown>;

  @Column({ type: 'enum', enum: PaymentMethod })
  paymentMethod: PaymentMethod;

  @Index()
  @Column({ type: 'enum', enum: PaymentStatus, default: PaymentStatus.PENDING })
  paymentStatus: PaymentStatus;

  // Money breakdown (paise)
  @Column({ type: 'int' })
  itemsSubtotal: number; // sum of line totals (GST-inclusive)

  @Column({ type: 'int', default: 0 })
  gstAmount: number; // GST portion within subtotal (for invoice)

  @Column({ type: 'int', default: 0 })
  deliveryCharge: number;

  @Column({ type: 'int', default: 0 })
  discountAmount: number;

  @Column({ type: 'int' })
  totalAmount: number; // what the buyer pays

  @OneToMany(() => OrderItem, (i) => i.order, { cascade: true })
  items: OrderItem[];

  @Column({ type: 'timestamptz' })
  placedAt: Date;
}
