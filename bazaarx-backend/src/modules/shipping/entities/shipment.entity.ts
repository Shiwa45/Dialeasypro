import { Entity, Column, Index, ManyToOne, JoinColumn } from 'typeorm';
import { BaseEntity } from '../../../common/entities/base.entity';
import { Order } from '../../orders/entities/order.entity';

export enum ShipmentStatus {
  CREATED = 'created', // SR order created
  AWB_ASSIGNED = 'awb_assigned', // courier + tracking number assigned
  PICKUP_SCHEDULED = 'pickup_scheduled',
  IN_TRANSIT = 'in_transit',
  OUT_FOR_DELIVERY = 'out_for_delivery',
  DELIVERED = 'delivered',
  RTO = 'rto', // return to origin
  CANCELLED = 'cancelled',
}

/**
 * A courier shipment for one seller's items in an order (created via
 * Shiprocket). Holds the gateway ids, AWB/courier, and live status.
 * One shipment can cover several order items going to the same address.
 */
@Entity('shipments')
@Index(['orderId', 'sellerId'])
export class Shipment extends BaseEntity {
  @Index()
  @ManyToOne(() => Order, { onDelete: 'CASCADE', nullable: false })
  @JoinColumn({ name: 'orderId' })
  order: Order;

  @Column({ type: 'uuid' })
  orderId: string;

  @Index()
  @Column({ type: 'uuid' })
  sellerId: string;

  // Shiprocket identifiers
  @Column({ type: 'varchar', length: 100, nullable: true })
  providerOrderId?: string;

  @Column({ type: 'varchar', length: 100, nullable: true })
  providerShipmentId?: string;

  @Index()
  @Column({ type: 'varchar', length: 100, nullable: true })
  awbCode?: string;

  @Column({ type: 'varchar', length: 120, nullable: true })
  courierName?: string;

  @Index()
  @Column({ type: 'enum', enum: ShipmentStatus, default: ShipmentStatus.CREATED })
  status: ShipmentStatus;

  @Column({ type: 'varchar', length: 6 })
  pickupPincode: string;

  @Column({ type: 'varchar', length: 6 })
  deliveryPincode: string;

  @Column({ type: 'int', default: 500 })
  weightGrams: number;

  @Column({ type: 'varchar', length: 1000, nullable: true })
  labelUrl?: string;

  @Column({ type: 'varchar', length: 1000, nullable: true })
  trackingUrl?: string;

  // Item ids covered by this shipment
  @Column({ type: 'jsonb', default: () => "'[]'" })
  orderItemIds: string[];

  // Frozen tracking history (latest event list from the provider)
  @Column({ type: 'jsonb', default: () => "'[]'" })
  trackingEvents: Array<Record<string, unknown>>;
}
