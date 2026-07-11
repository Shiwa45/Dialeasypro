import { Entity, Column, Index, ManyToOne, JoinColumn } from 'typeorm';
import { BaseEntity } from '../../../common/entities/base.entity';
import { Order } from './order.entity';

/**
 * Per-item fulfillment lifecycle. Each seller advances their own items:
 * placed → confirmed → packed → shipped → out_for_delivery → delivered.
 * Buyers may cancel before dispatch (placed/confirmed).
 */
export enum OrderItemStatus {
  PENDING_PAYMENT = 'pending_payment', // online order awaiting payment
  PLACED = 'placed',
  CONFIRMED = 'confirmed',
  PACKED = 'packed',
  SHIPPED = 'shipped',
  OUT_FOR_DELIVERY = 'out_for_delivery',
  DELIVERED = 'delivered',
  CANCELLED = 'cancelled',
  RETURNED = 'returned',
}

@Entity('order_items')
export class OrderItem extends BaseEntity {
  @Index()
  @ManyToOne(() => Order, (o) => o.items, {
    onDelete: 'CASCADE',
    nullable: false,
  })
  @JoinColumn({ name: 'orderId' })
  order: Order;

  @Column({ type: 'uuid' })
  orderId: string;

  @Index()
  @Column({ type: 'uuid' })
  sellerId: string;

  @Column({ type: 'uuid' })
  productId: string;

  @Column({ type: 'uuid' })
  variantId: string;

  // --- snapshots at order time (immutable history) ---
  @Column({ type: 'varchar', length: 300 })
  productTitle: string;

  @Column({ type: 'varchar', length: 100 })
  sku: string;

  @Column({ type: 'varchar', length: 8, default: '9999' })
  hsnCode: string;

  @Column({ type: 'jsonb', default: () => "'{}'" })
  attributes: Record<string, string>;

  @Column({ type: 'varchar', length: 1000, nullable: true })
  imageUrl?: string;

  @Column({ type: 'int' })
  unitPrice: number; // GST-inclusive price per unit (paise)

  @Column({ type: 'int' })
  quantity: number;

  @Column({ type: 'decimal', precision: 5, scale: 2 })
  gstRate: number; // % applied

  @Column({ type: 'int' })
  gstAmount: number; // GST portion of the line (paise)

  @Column({ type: 'int' })
  lineTotal: number; // unitPrice * quantity (paise)

  @Index()
  @Column({
    type: 'enum',
    enum: OrderItemStatus,
    default: OrderItemStatus.PLACED,
  })
  status: OrderItemStatus;

  @Column({ type: 'varchar', length: 100, nullable: true })
  awbNumber?: string; // tracking number once shipped

  @Column({ type: 'varchar', length: 500, nullable: true })
  cancelReason?: string;
}
