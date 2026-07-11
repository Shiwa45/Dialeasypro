import { Injectable } from '@nestjs/common';
import { OnEvent } from '@nestjs/event-emitter';
import { NotificationService } from '../services/notification.service';
import { NotificationType } from '../entities/notification.entity';
import {
  NotifyEvents,
  OrderPlacedPayload,
  PaymentSucceededPayload,
  ShipmentPayload,
  ReturnPayload,
} from '../notification.events';

const rupees = (paise: number) =>
  '₹' + (paise / 100).toLocaleString('en-IN', { minimumFractionDigits: 2 });

@Injectable()
export class NotificationListener {
  constructor(private readonly notifications: NotificationService) {}

  @OnEvent(NotifyEvents.ORDER_PLACED)
  async onOrderPlaced(p: OrderPlacedPayload) {
    await this.notifications.notify({
      userId: p.userId,
      type: NotificationType.ORDER_PLACED,
      title: 'Order placed',
      body: `Your order ${p.orderNumber} for ${rupees(p.totalAmount)} has been placed.`,
      data: { orderId: p.orderId, orderNumber: p.orderNumber },
    });
    // Notify each seller of a new order to fulfil
    for (const sellerId of [...new Set(p.sellerIds)]) {
      await this.notifications.notify({
        userId: sellerId,
        type: NotificationType.SELLER_NEW_ORDER,
        title: 'New order received',
        body: `You have new item(s) to fulfil in order ${p.orderNumber}.`,
        data: { orderId: p.orderId },
      });
    }
  }

  @OnEvent(NotifyEvents.PAYMENT_SUCCEEDED)
  async onPaymentSucceeded(p: PaymentSucceededPayload) {
    await this.notifications.notify({
      userId: p.userId,
      type: NotificationType.PAYMENT_SUCCESS,
      title: 'Payment successful',
      body: `We received ${rupees(p.amount)} for order ${p.orderNumber}.`,
      data: { orderId: p.orderId },
    });
  }

  @OnEvent(NotifyEvents.ORDER_SHIPPED)
  async onShipped(p: ShipmentPayload) {
    await this.notifications.notify({
      userId: p.userId,
      type: NotificationType.ORDER_SHIPPED,
      title: 'Order shipped',
      body: `Order ${p.orderNumber} is on its way${p.courierName ? ` via ${p.courierName}` : ''}${p.awbCode ? ` (AWB ${p.awbCode})` : ''}.`,
      data: { orderId: p.orderId, awbCode: p.awbCode },
    });
  }

  @OnEvent(NotifyEvents.ORDER_DELIVERED)
  async onDelivered(p: ShipmentPayload) {
    await this.notifications.notify({
      userId: p.userId,
      type: NotificationType.ORDER_DELIVERED,
      title: 'Order delivered',
      body: `Order ${p.orderNumber} has been delivered. Enjoy!`,
      data: { orderId: p.orderId },
    });
  }

  @OnEvent(NotifyEvents.RETURN_REQUESTED)
  async onReturnRequested(p: ReturnPayload) {
    await this.notifications.notify({
      userId: p.buyerId,
      type: NotificationType.RETURN_REQUESTED,
      title: 'Return requested',
      body: `Your return ${p.returnNumber} has been submitted.`,
      data: { returnId: p.returnId },
    });
  }

  @OnEvent(NotifyEvents.RETURN_APPROVED)
  async onReturnApproved(p: ReturnPayload) {
    await this.notifications.notify({
      userId: p.buyerId,
      type: NotificationType.RETURN_APPROVED,
      title: 'Return approved',
      body: `Return ${p.returnNumber} is approved; a pickup has been scheduled.`,
      data: { returnId: p.returnId },
    });
  }

  @OnEvent(NotifyEvents.REFUND_PROCESSED)
  async onRefund(p: ReturnPayload) {
    await this.notifications.notify({
      userId: p.buyerId,
      type: NotificationType.REFUND_PROCESSED,
      title: 'Refund processed',
      body: `A refund of ${rupees(p.refundAmount ?? 0)} for ${p.returnNumber} has been initiated.`,
      data: { returnId: p.returnId },
    });
  }
}
