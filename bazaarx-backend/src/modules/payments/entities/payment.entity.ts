import { Entity, Column, Index, ManyToOne, JoinColumn } from 'typeorm';
import { BaseEntity } from '../../../common/entities/base.entity';
import { Order } from '../../orders/entities/order.entity';

export enum PaymentGateway {
  RAZORPAY = 'razorpay',
}

export enum PaymentRecordStatus {
  CREATED = 'created', // gateway order created, awaiting payment
  CAPTURED = 'captured', // payment succeeded & verified
  FAILED = 'failed',
  REFUNDED = 'refunded',
}

/**
 * One payment attempt against an order. Tracks the gateway's order/payment
 * ids and the verified outcome. The gateway order id is what the client
 * uses to open the Razorpay checkout; the payment id + signature come back
 * after the user pays and are verified server-side.
 */
@Entity('payments')
export class Payment extends BaseEntity {
  @Index()
  @ManyToOne(() => Order, { onDelete: 'CASCADE', nullable: false })
  @JoinColumn({ name: 'orderId' })
  order: Order;

  @Column({ type: 'uuid' })
  orderId: string;

  @Column({ type: 'enum', enum: PaymentGateway, default: PaymentGateway.RAZORPAY })
  gateway: PaymentGateway;

  @Index({ unique: true })
  @Column({ type: 'varchar', length: 100 })
  gatewayOrderId: string; // e.g. order_XXXXXXXX

  @Column({ type: 'varchar', length: 100, nullable: true })
  gatewayPaymentId?: string; // e.g. pay_XXXXXXXX

  @Column({ type: 'int' })
  amount: number; // paise

  @Column({ type: 'varchar', length: 3, default: 'INR' })
  currency: string;

  @Index()
  @Column({
    type: 'enum',
    enum: PaymentRecordStatus,
    default: PaymentRecordStatus.CREATED,
  })
  status: PaymentRecordStatus;

  @Column({ type: 'varchar', length: 50, nullable: true })
  method?: string; // upi / card / netbanking (reported by gateway)

  @Column({ type: 'varchar', length: 100, nullable: true })
  errorCode?: string;

  @Column({ type: 'varchar', length: 500, nullable: true })
  errorDescription?: string;
}
