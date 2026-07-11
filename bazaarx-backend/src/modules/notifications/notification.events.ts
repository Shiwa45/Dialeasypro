/**
 * Domain events that trigger notifications. Emitted by the order,
 * payment, shipping, and return flows; consumed by NotificationListener.
 * Decoupled via the global event bus — emitters never import the
 * notifications module.
 */
export const NotifyEvents = {
  ORDER_PLACED: 'notify.order.placed',
  PAYMENT_SUCCEEDED: 'notify.payment.succeeded',
  ORDER_SHIPPED: 'notify.order.shipped',
  ORDER_DELIVERED: 'notify.order.delivered',
  RETURN_REQUESTED: 'notify.return.requested',
  RETURN_APPROVED: 'notify.return.approved',
  REFUND_PROCESSED: 'notify.refund.processed',
} as const;

export interface OrderPlacedPayload {
  orderId: string;
  userId: string;
  orderNumber: string;
  totalAmount: number;
  sellerIds: string[];
}
export interface PaymentSucceededPayload {
  orderId: string;
  userId: string;
  orderNumber: string;
  amount: number;
}
export interface ShipmentPayload {
  orderId: string;
  userId: string;
  orderNumber: string;
  awbCode?: string;
  courierName?: string;
}
export interface ReturnPayload {
  returnId: string;
  buyerId: string;
  returnNumber: string;
  refundAmount?: number;
}
