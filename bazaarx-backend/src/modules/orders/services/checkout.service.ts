import {
  Injectable,
  BadRequestException,
} from '@nestjs/common';
import { DataSource } from 'typeorm';
import { CartService } from '../../cart/cart.service';
import { AddressService } from '../../users/address.service';
import { ProductVariant } from '../../catalog/entities/product-variant.entity';
import { Category } from '../../catalog/entities/category.entity';
import { Order, PaymentMethod, PaymentStatus } from '../entities/order.entity';
import { OrderItem, OrderItemStatus } from '../entities/order-item.entity';
import { CheckoutDto } from '../dto/order.dto';
import { generateOrderNumber } from '../../../common/utils/order-number.util';
import { PaymentService } from '../../payments/services/payment.service';
import { GatewayOrder } from '../../payments/services/razorpay.service';
import { CouponService } from '../../promotions/services/coupon.service';
import { EventEmitter2 } from '@nestjs/event-emitter';
import { NotifyEvents } from '../../notifications/notification.events';
import { WalletService } from '../../wallet/services/wallet.service';
import { WalletTxnSource } from '../../wallet/entities/wallet.entity';

const FREE_DELIVERY_THRESHOLD = 49900; // ₹499 in paise
const DELIVERY_CHARGE = 4000; // ₹40 in paise

@Injectable()
export class CheckoutService {
  constructor(
    private readonly cart: CartService,
    private readonly addresses: AddressService,
    private readonly payments: PaymentService,
    private readonly coupons: CouponService,
    private readonly wallet: WalletService,
    private readonly events: EventEmitter2,
    private readonly dataSource: DataSource,
  ) {}

  /**
   * Converts the user's cart into an order:
   *  - validates address ownership
   *  - atomically decrements stock (prevents overselling under load)
   *  - snapshots price + GST per item (immutable order history)
   *  - computes totals + delivery charge
   *  - clears the cart on success
   */
  async placeOrder(
    userId: string,
    dto: CheckoutDto,
  ): Promise<{ order: Order; payment: GatewayOrder | null }> {
    const cart = await this.cart.getCart(userId);
    if (cart.items.length === 0) {
      throw new BadRequestException('Your cart is empty');
    }

    // Validates the address belongs to this user (throws otherwise)
    const address = await this.addresses.findOneForUser(userId, dto.addressId);

    // Validate coupon (if any) against the cart before we touch stock
    const couponResult = dto.couponCode
      ? await this.coupons.validateAndCompute(
          dto.couponCode,
          userId,
          cart.items.map((i) => ({
            productId: i.productId,
            lineTotal: i.lineTotal,
          })),
        )
      : null;

    const gatewayMethods = [
      PaymentMethod.UPI,
      PaymentMethod.CARD,
      PaymentMethod.NETBANKING,
    ];
    const isGateway = gatewayMethods.includes(dto.paymentMethod);
    // Gateway orders hold items until payment clears; everything else
    // (COD/wallet/BNPL) releases items immediately.
    const initialItemStatus = isGateway
      ? OrderItemStatus.PENDING_PAYMENT
      : OrderItemStatus.PLACED;

    const order = await this.dataSource.transaction(async (manager) => {
      const orderItems: OrderItem[] = [];
      let itemsSubtotal = 0;
      let gstTotal = 0;

      for (const line of cart.items) {
        // Atomic conditional decrement — only succeeds if enough stock.
        const dec = await manager
          .createQueryBuilder()
          .update(ProductVariant)
          .set({ stockQuantity: () => `"stockQuantity" - ${line.quantity}` })
          .where('id = :id AND "stockQuantity" >= :qty', {
            id: line.variantId,
            qty: line.quantity,
          })
          .execute();

        if (dec.affected !== 1) {
          // Rolls back everything decremented so far
          throw new BadRequestException(
            `Insufficient stock for "${line.title}". Please review your cart.`,
          );
        }

        const variant = await manager.findOne(ProductVariant, {
          where: { id: line.variantId },
          relations: ['product'],
        });
        if (!variant) {
          throw new BadRequestException('A product in your cart is unavailable');
        }
        const category = await manager.findOne(Category, {
          where: { id: variant.product.categoryId },
        });
        const gstRate = Number(category?.gstRate ?? 0);

        const unitPrice = variant.sellingPrice; // GST-inclusive
        const lineTotal = unitPrice * line.quantity;
        // Extract the GST portion from a GST-inclusive price
        const base = Math.round(unitPrice / (1 + gstRate / 100));
        const gstAmount = (unitPrice - base) * line.quantity;

        itemsSubtotal += lineTotal;
        gstTotal += gstAmount;

        orderItems.push(
          manager.create(OrderItem, {
            sellerId: variant.product.sellerId,
            productId: variant.productId,
            variantId: variant.id,
            productTitle: variant.product.title,
            sku: variant.sku,
            hsnCode: variant.product.hsnCode ?? '9999',
            attributes: variant.attributes,
            imageUrl: variant.imageUrls?.[0],
            unitPrice,
            quantity: line.quantity,
            gstRate,
            gstAmount,
            lineTotal,
            status: initialItemStatus,
          }),
        );
      }

      const deliveryCharge =
        itemsSubtotal >= FREE_DELIVERY_THRESHOLD ? 0 : DELIVERY_CHARGE;
      const discountAmount = couponResult
        ? Math.min(couponResult.discount, itemsSubtotal)
        : 0;
      const totalAmount = itemsSubtotal + deliveryCharge - discountAmount;

      const newOrder = manager.create(Order, {
        orderNumber: generateOrderNumber(),
        userId,
        shippingAddress: {
          name: address.name,
          mobile: address.mobile,
          line1: address.line1,
          line2: address.line2,
          city: address.city,
          state: address.state,
          pincode: address.pincode,
          landmark: address.landmark,
        },
        paymentMethod: dto.paymentMethod,
        paymentStatus:
          dto.paymentMethod === PaymentMethod.WALLET ||
          dto.paymentMethod === PaymentMethod.BNPL
            ? PaymentStatus.PAID
            : PaymentStatus.PENDING,
        itemsSubtotal,
        gstAmount: gstTotal,
        deliveryCharge,
        discountAmount,
        totalAmount,
        placedAt: new Date(),
      });

      const savedOrder = await manager.save(newOrder);
      orderItems.forEach((i) => (i.orderId = savedOrder.id));
      await manager.save(orderItems);
      savedOrder.items = orderItems;

      // Settle internal payment methods within the same transaction
      if (dto.paymentMethod === PaymentMethod.WALLET) {
        await this.wallet.debitTx(
          manager,
          userId,
          totalAmount,
          WalletTxnSource.PURCHASE,
          savedOrder.id,
          `Order ${savedOrder.orderNumber}`,
        );
      } else if (dto.paymentMethod === PaymentMethod.BNPL) {
        await this.wallet.bnplChargeTx(
          manager,
          userId,
          totalAmount,
          savedOrder.id,
        );
      }

      // Record coupon redemption within the same transaction
      if (couponResult) {
        await this.coupons.redeem(
          manager,
          couponResult.coupon,
          userId,
          savedOrder.id,
          discountAmount,
        );
      }
      return savedOrder;
    });

    // Cart is Redis-side; clear only after the DB transaction commits
    await this.cart.clear(userId);

    this.events.emit(NotifyEvents.ORDER_PLACED, {
      orderId: order.id,
      userId,
      orderNumber: order.orderNumber,
      totalAmount: order.totalAmount,
      sellerIds: [...new Set(order.items.map((i) => i.sellerId))],
    });

    // COD/wallet/BNPL: nothing more. Gateway methods: create a gateway order.
    if (!isGateway) {
      return { order, payment: null };
    }
    const gateway = await this.payments.createForOrder(order);
    return { order, payment: gateway };
  }
}
