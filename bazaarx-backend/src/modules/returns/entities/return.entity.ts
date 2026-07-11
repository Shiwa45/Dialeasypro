import { Entity, Column, Index, ManyToOne, JoinColumn } from 'typeorm';
import { BaseEntity } from '../../../common/entities/base.entity';
import { Order } from '../../orders/entities/order.entity';
import { OrderItem } from '../../orders/entities/order-item.entity';

export enum ReturnStatus {
  REQUESTED = 'requested', // buyer raised it
  APPROVED = 'approved', // seller/admin approved → reverse pickup created
  REJECTED = 'rejected',
  PICKED_UP = 'picked_up', // reverse shipment collected
  RECEIVED = 'received', // item back with seller
  REFUNDED = 'refunded', // money returned
  CANCELLED = 'cancelled', // buyer withdrew
}

export enum ReturnReason {
  DAMAGED = 'damaged',
  DEFECTIVE = 'defective',
  WRONG_ITEM = 'wrong_item',
  NOT_AS_DESCRIBED = 'not_as_described',
  SIZE_FIT = 'size_fit',
  NO_LONGER_NEEDED = 'no_longer_needed',
}

export enum RefundMethod {
  RAZORPAY = 'razorpay', // back to original online payment
  WALLET = 'wallet', // COD → store wallet / source
}

/**
 * A return/refund request against one delivered order item.
 * Tracks the lifecycle from request → approval → refund, plus the
 * reverse-pickup AWB and the refund reference.
 */
@Entity('returns')
export class Return extends BaseEntity {
  @Index({ unique: true })
  @Column({ type: 'varchar', length: 30, unique: true })
  returnNumber: string; // RET-2026-XXXXXXXX

  @Index()
  @ManyToOne(() => Order, { onDelete: 'CASCADE', nullable: false })
  @JoinColumn({ name: 'orderId' })
  order: Order;

  @Column({ type: 'uuid' })
  orderId: string;

  @Index()
  @ManyToOne(() => OrderItem, { onDelete: 'CASCADE', nullable: false })
  @JoinColumn({ name: 'orderItemId' })
  orderItem: OrderItem;

  @Column({ type: 'uuid' })
  orderItemId: string;

  @Index()
  @Column({ type: 'uuid' })
  buyerId: string;

  @Index()
  @Column({ type: 'uuid' })
  sellerId: string;

  @Column({ type: 'enum', enum: ReturnReason })
  reason: ReturnReason;

  @Column({ type: 'varchar', length: 1000, nullable: true })
  comments?: string;

  @Index()
  @Column({ type: 'enum', enum: ReturnStatus, default: ReturnStatus.REQUESTED })
  status: ReturnStatus;

  @Column({ type: 'varchar', length: 500, nullable: true })
  rejectionReason?: string;

  // Reverse pickup
  @Column({ type: 'varchar', length: 100, nullable: true })
  reverseAwb?: string;

  // Refund
  @Column({ type: 'int' })
  refundAmount: number; // paise

  @Column({ type: 'enum', enum: RefundMethod, nullable: true })
  refundMethod?: RefundMethod;

  @Column({ type: 'varchar', length: 100, nullable: true })
  refundReference?: string;

  @Column({ type: 'timestamptz', nullable: true })
  refundedAt?: Date;
}
