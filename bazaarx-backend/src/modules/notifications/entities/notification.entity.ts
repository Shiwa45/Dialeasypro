import { Entity, Column, Index } from 'typeorm';
import { BaseEntity } from '../../../common/entities/base.entity';

export enum NotificationType {
  ORDER_PLACED = 'order_placed',
  PAYMENT_SUCCESS = 'payment_success',
  PAYMENT_FAILED = 'payment_failed',
  ORDER_SHIPPED = 'order_shipped',
  ORDER_DELIVERED = 'order_delivered',
  RETURN_REQUESTED = 'return_requested',
  RETURN_APPROVED = 'return_approved',
  REFUND_PROCESSED = 'refund_processed',
  SELLER_NEW_ORDER = 'seller_new_order',
}

/**
 * An in-app notification (the user's inbox). The same content may also
 * be dispatched over SMS/email/push depending on the user's preferences.
 */
@Entity('notifications')
export class Notification extends BaseEntity {
  @Index()
  @Column({ type: 'uuid' })
  userId: string;

  @Column({ type: 'enum', enum: NotificationType })
  type: NotificationType;

  @Column({ type: 'varchar', length: 200 })
  title: string;

  @Column({ type: 'varchar', length: 1000 })
  body: string;

  // Contextual payload (orderId, etc.) for deep-linking in the app
  @Column({ type: 'jsonb', default: () => "'{}'" })
  data: Record<string, unknown>;

  @Index()
  @Column({ type: 'boolean', default: false })
  isRead: boolean;

  @Column({ type: 'timestamptz', nullable: true })
  readAt?: Date;
}
