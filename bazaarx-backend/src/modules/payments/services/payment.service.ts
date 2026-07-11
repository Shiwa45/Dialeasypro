import {
  Injectable,
  Logger,
  NotFoundException,
  ForbiddenException,
  BadRequestException,
} from '@nestjs/common';
import { InjectRepository } from '@nestjs/typeorm';
import { DataSource, Repository } from 'typeorm';
import {
  Payment,
  PaymentGateway,
  PaymentRecordStatus,
} from '../entities/payment.entity';
import { Order, PaymentStatus } from '../../orders/entities/order.entity';
import { OrderItem, OrderItemStatus } from '../../orders/entities/order-item.entity';
import { ProductVariant } from '../../catalog/entities/product-variant.entity';
import { RazorpayService, GatewayOrder } from './razorpay.service';
import { EventEmitter2 } from '@nestjs/event-emitter';
import { NotifyEvents } from '../../notifications/notification.events';

@Injectable()
export class PaymentService {
  private readonly logger = new Logger('PaymentService');

  constructor(
    @InjectRepository(Payment)
    private readonly paymentRepo: Repository<Payment>,
    private readonly razorpay: RazorpayService,
    private readonly events: EventEmitter2,
    private readonly dataSource: DataSource,
  ) {}

  /** Creates a gateway order + payment record for an existing order. */
  async createForOrder(order: Order): Promise<GatewayOrder & { paymentId: string }> {
    const gw = await this.razorpay.createOrder(
      order.totalAmount,
      order.orderNumber,
    );
    const payment = await this.paymentRepo.save(
      this.paymentRepo.create({
        orderId: order.id,
        gateway: PaymentGateway.RAZORPAY,
        gatewayOrderId: gw.gatewayOrderId,
        amount: order.totalAmount,
        currency: gw.currency,
        status: PaymentRecordStatus.CREATED,
      }),
    );
    return { ...gw, paymentId: payment.id };
  }

  /**
   * Verifies a completed payment (called by the client after Razorpay
   * checkout). On success: marks the order paid and releases the items
   * for fulfillment (PENDING_PAYMENT → PLACED). Idempotent.
   */
  async verify(
    userId: string,
    gatewayOrderId: string,
    gatewayPaymentId: string,
    signature: string,
  ): Promise<{ orderId: string; paymentStatus: PaymentStatus }> {
    const payment = await this.paymentRepo.findOne({
      where: { gatewayOrderId },
      relations: ['order'],
    });
    if (!payment) throw new NotFoundException('Payment not found');
    if (payment.order.userId !== userId) {
      throw new ForbiddenException('Not your payment');
    }

    // Idempotency: already captured → just return current state
    if (payment.status === PaymentRecordStatus.CAPTURED) {
      return {
        orderId: payment.orderId,
        paymentStatus: PaymentStatus.PAID,
      };
    }

    const valid = this.razorpay.verifyPaymentSignature(
      gatewayOrderId,
      gatewayPaymentId,
      signature,
    );
    if (!valid) {
      throw new BadRequestException('Invalid payment signature');
    }

    await this.capture(payment.orderId, gatewayOrderId, gatewayPaymentId);
    return { orderId: payment.orderId, paymentStatus: PaymentStatus.PAID };
  }

  /**
   * Handles a Razorpay webhook (server-to-server, authoritative).
   * Verifies the body signature then applies the event idempotently.
   */
  async handleWebhook(rawBody: string, signature: string): Promise<void> {
    if (!this.razorpay.verifyWebhookSignature(rawBody, signature)) {
      throw new BadRequestException('Invalid webhook signature');
    }
    const event = JSON.parse(rawBody);
    const entity = event?.payload?.payment?.entity;
    if (!entity) return;

    const gatewayOrderId = entity.order_id;
    const gatewayPaymentId = entity.id;

    if (event.event === 'payment.captured') {
      const payment = await this.paymentRepo.findOne({
        where: { gatewayOrderId },
      });
      if (payment && payment.status !== PaymentRecordStatus.CAPTURED) {
        await this.capture(payment.orderId, gatewayOrderId, gatewayPaymentId, entity.method);
      }
    } else if (event.event === 'payment.failed') {
      await this.markFailed(
        gatewayOrderId,
        entity.error_code,
        entity.error_description,
      );
    }
  }

  /** Marks a payment failed and restores reserved stock. */
  async markFailed(
    gatewayOrderId: string,
    errorCode?: string,
    errorDescription?: string,
  ): Promise<void> {
    const payment = await this.paymentRepo.findOne({
      where: { gatewayOrderId },
    });
    if (!payment || payment.status === PaymentRecordStatus.CAPTURED) return;

    await this.dataSource.transaction(async (manager) => {
      payment.status = PaymentRecordStatus.FAILED;
      payment.errorCode = errorCode;
      payment.errorDescription = errorDescription;
      await manager.save(payment);

      const order = await manager.findOne(Order, {
        where: { id: payment.orderId },
        relations: ['items'],
      });
      if (!order) return;
      order.paymentStatus = PaymentStatus.FAILED;
      await manager.save(order);

      // Release reserved stock and cancel the unpaid items
      for (const item of order.items) {
        if (item.status === OrderItemStatus.PENDING_PAYMENT) {
          await manager
            .createQueryBuilder()
            .update(ProductVariant)
            .set({ stockQuantity: () => `"stockQuantity" + ${item.quantity}` })
            .where('id = :id', { id: item.variantId })
            .execute();
          item.status = OrderItemStatus.CANCELLED;
          item.cancelReason = 'Payment failed';
          await manager.save(item);
        }
      }
    });
    this.logger.warn(`Payment failed for ${gatewayOrderId}: ${errorCode}`);
  }

  /**
   * Issues a refund for an order (used by returns). For prepaid orders it
   * refunds the captured gateway payment; for COD there's no gateway
   * payment, so the caller records a wallet/source refund instead.
   * Returns null when there's no captured payment (e.g. COD).
   */
  async refund(
    orderId: string,
    amountPaise: number,
  ): Promise<{ refundId: string; method: string } | null> {
    const payment = await this.paymentRepo.findOne({
      where: { orderId, status: PaymentRecordStatus.CAPTURED },
    });
    if (!payment || !payment.gatewayPaymentId) {
      return null; // COD or no captured payment
    }
    const { refundId } = await this.razorpay.refund(
      payment.gatewayPaymentId,
      amountPaise,
    );
    return { refundId, method: payment.gateway };
  }

  /** Shared capture logic (verify + webhook). Idempotent at the caller. */
  private async capture(
    orderId: string,
    gatewayOrderId: string,
    gatewayPaymentId: string,
    method?: string,
  ): Promise<void> {
    await this.dataSource.transaction(async (manager) => {
      await manager.update(
        Payment,
        { gatewayOrderId },
        {
          status: PaymentRecordStatus.CAPTURED,
          gatewayPaymentId,
          method,
        },
      );
      await manager.update(
        Order,
        { id: orderId },
        { paymentStatus: PaymentStatus.PAID },
      );
      // Release items for fulfillment
      await manager.update(
        OrderItem,
        { orderId, status: OrderItemStatus.PENDING_PAYMENT },
        { status: OrderItemStatus.PLACED },
      );
    });
    this.logger.log(`Payment captured for order ${orderId}`);

    const order = await this.paymentRepo.manager.findOne(Order, {
      where: { id: orderId },
    });
    if (order) {
      this.events.emit(NotifyEvents.PAYMENT_SUCCEEDED, {
        orderId,
        userId: order.userId,
        orderNumber: order.orderNumber,
        amount: order.totalAmount,
      });
    }
  }
}
