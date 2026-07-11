import { Entity, Column, Index, ManyToOne, JoinColumn } from 'typeorm';
import { BaseEntity } from '../../../common/entities/base.entity';
import { Order } from '../../orders/entities/order.entity';

/**
 * A GST tax invoice for one seller's items within an order.
 * In a marketplace each seller issues their own invoice under their
 * GSTIN, so an order with N sellers produces N invoices.
 *
 * The fully computed invoice (line items, tax split, totals) is frozen
 * as JSON so the PDF can be regenerated identically at any time.
 */
@Entity('invoices')
@Index(['orderId', 'sellerId'], { unique: true })
export class Invoice extends BaseEntity {
  @Index({ unique: true })
  @Column({ type: 'varchar', length: 40, unique: true })
  invoiceNumber: string; // e.g. INV-2026-00000042

  @Index()
  @ManyToOne(() => Order, { onDelete: 'CASCADE', nullable: false })
  @JoinColumn({ name: 'orderId' })
  order: Order;

  @Column({ type: 'uuid' })
  orderId: string;

  @Index()
  @Column({ type: 'uuid' })
  sellerId: string;

  // Frozen, fully-computed invoice payload (used to render the PDF)
  @Column({ type: 'jsonb' })
  data: Record<string, unknown>;

  @Column({ type: 'boolean', default: false })
  isIntraState: boolean;

  @Column({ type: 'int' })
  taxableValue: number; // paise

  @Column({ type: 'int' })
  totalTax: number; // paise (CGST+SGST or IGST)

  @Column({ type: 'int' })
  grandTotal: number; // paise

  @Column({ type: 'timestamptz' })
  issuedAt: Date;
}
