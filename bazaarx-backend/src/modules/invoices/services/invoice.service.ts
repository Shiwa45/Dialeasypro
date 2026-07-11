import {
  Injectable,
  NotFoundException,
  ForbiddenException,
  BadRequestException,
} from '@nestjs/common';
import { InjectRepository } from '@nestjs/typeorm';
import { Repository } from 'typeorm';
import { Invoice } from '../entities/invoice.entity';
import { Order } from '../../orders/entities/order.entity';
import { OrderItem, OrderItemStatus } from '../../orders/entities/order-item.entity';
import { Seller } from '../../sellers/entities/seller.entity';
import { UserRole } from '../../users/entities/user.entity';
import { InvoicePdfService, InvoiceData } from './invoice-pdf.service';
import { isIntraState, stateFromGstin } from '../../../common/utils/gst-state-codes.util';

@Injectable()
export class InvoiceService {
  constructor(
    @InjectRepository(Invoice)
    private readonly invoiceRepo: Repository<Invoice>,
    @InjectRepository(Order)
    private readonly orderRepo: Repository<Order>,
    @InjectRepository(Seller)
    private readonly sellerRepo: Repository<Seller>,
    private readonly pdf: InvoicePdfService,
  ) {}

  /** Lists invoices visible to the requester for an order. */
  async listForOrder(
    orderId: string,
    requesterId: string,
    role: UserRole,
  ): Promise<Invoice[]> {
    const order = await this.orderRepo.findOne({ where: { id: orderId } });
    if (!order) throw new NotFoundException('Order not found');
    if (role !== UserRole.ADMIN && order.userId !== requesterId) {
      // sellers see only their own invoice via the seller filter below
      if (role !== UserRole.SELLER) throw new ForbiddenException('Not allowed');
    }
    const where =
      role === UserRole.SELLER
        ? { orderId, sellerId: requesterId }
        : { orderId };
    return this.invoiceRepo.find({ where, order: { createdAt: 'ASC' } });
  }

  /** Generates (or returns) the PDF for one seller's invoice in an order. */
  async getPdf(
    orderId: string,
    sellerId: string,
    requesterId: string,
    role: UserRole,
  ): Promise<{ invoice: Invoice; pdf: Buffer }> {
    const order = await this.orderRepo.findOne({
      where: { id: orderId },
      relations: ['items'],
    });
    if (!order) throw new NotFoundException('Order not found');

    // Authorization: buyer who owns the order, the seller in question, or admin
    const isOwner = order.userId === requesterId;
    const isThisSeller = role === UserRole.SELLER && requesterId === sellerId;
    if (role !== UserRole.ADMIN && !isOwner && !isThisSeller) {
      throw new ForbiddenException('Not allowed to access this invoice');
    }

    let invoice = await this.invoiceRepo.findOne({
      where: { orderId, sellerId },
    });
    if (!invoice) {
      invoice = await this.generate(order, sellerId);
    }

    const pdf = await this.pdf.render(invoice.data as unknown as InvoiceData);
    return { invoice, pdf };
  }

  /** Computes and persists an invoice for one seller's items in an order. */
  private async generate(order: Order, sellerId: string): Promise<Invoice> {
    const items = order.items.filter(
      (i) => i.sellerId === sellerId && i.status !== OrderItemStatus.CANCELLED,
    );
    if (items.length === 0) {
      throw new BadRequestException(
        'No billable items for this seller in this order',
      );
    }

    const seller = await this.sellerRepo.findOne({ where: { userId: sellerId } });
    if (!seller) throw new NotFoundException('Seller profile not found');

    const buyerState = (order.shippingAddress.state as string) ?? '';
    const intra = isIntraState(seller.gstin, buyerState);

    const lines = items.map((it) => {
      const taxable = it.lineTotal - it.gstAmount;
      return {
        title: it.productTitle,
        hsnCode: it.hsnCode,
        quantity: it.quantity,
        taxableValue: taxable,
        gstRate: Number(it.gstRate),
        cgst: intra ? Math.round(it.gstAmount / 2) : 0,
        sgst: intra ? it.gstAmount - Math.round(it.gstAmount / 2) : 0,
        igst: intra ? 0 : it.gstAmount,
        lineTotal: it.lineTotal,
      };
    });

    const taxableValue = lines.reduce((s, l) => s + l.taxableValue, 0);
    const totalCgst = lines.reduce((s, l) => s + l.cgst, 0);
    const totalSgst = lines.reduce((s, l) => s + l.sgst, 0);
    const totalIgst = lines.reduce((s, l) => s + l.igst, 0);
    const totalTax = totalCgst + totalSgst + totalIgst;
    const grandTotal = lines.reduce((s, l) => s + l.lineTotal, 0);

    const invoiceNumber = await this.nextInvoiceNumber();
    const issuedAt = new Date();

    const data: InvoiceData = {
      invoiceNumber,
      issuedAt: issuedAt.toISOString(),
      orderNumber: order.orderNumber,
      isIntraState: intra,
      seller: {
        businessName: seller.businessName,
        gstin: seller.gstin,
        stateName: stateFromGstin(seller.gstin),
      },
      buyer: {
        name: (order.shippingAddress.name as string) ?? '',
        address: [
          order.shippingAddress.line1,
          order.shippingAddress.line2,
          order.shippingAddress.city,
        ]
          .filter(Boolean)
          .join(', '),
        state: buyerState,
        pincode: (order.shippingAddress.pincode as string) ?? '',
      },
      lines,
      taxableValue,
      totalCgst,
      totalSgst,
      totalIgst,
      totalTax,
      grandTotal,
    };

    const invoice = this.invoiceRepo.create({
      invoiceNumber,
      orderId: order.id,
      sellerId,
      data: data as unknown as Record<string, unknown>,
      isIntraState: intra,
      taxableValue,
      totalTax,
      grandTotal,
      issuedAt,
    });
    return this.invoiceRepo.save(invoice);
  }

  /** Sequential invoice number: INV-<year>-<8-digit counter>. */
  private async nextInvoiceNumber(): Promise<string> {
    const year = new Date().getFullYear();
    const count = await this.invoiceRepo.count();
    const seq = String(count + 1).padStart(8, '0');
    return `INV-${year}-${seq}`;
  }
}
