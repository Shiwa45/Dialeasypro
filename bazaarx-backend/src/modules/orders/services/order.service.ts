import {
  Injectable,
  NotFoundException,
  ForbiddenException,
  BadRequestException,
} from '@nestjs/common';
import { InjectRepository } from '@nestjs/typeorm';
import { DataSource, Repository } from 'typeorm';
import { Order, PaymentStatus, PaymentMethod } from '../entities/order.entity';
import { OrderItem, OrderItemStatus } from '../entities/order-item.entity';
import { ProductVariant } from '../../catalog/entities/product-variant.entity';
import { paginate } from '../../../common/dto/paginated-result';
import { PaginationQueryDto } from '../../../common/dto/pagination-query.dto';

/** Allowed seller-driven forward transitions. */
const SELLER_TRANSITIONS: Record<OrderItemStatus, OrderItemStatus[]> = {
  [OrderItemStatus.PENDING_PAYMENT]: [], // released to PLACED only by payment capture
  [OrderItemStatus.PLACED]: [OrderItemStatus.CONFIRMED],
  [OrderItemStatus.CONFIRMED]: [OrderItemStatus.PACKED],
  [OrderItemStatus.PACKED]: [OrderItemStatus.SHIPPED],
  [OrderItemStatus.SHIPPED]: [OrderItemStatus.OUT_FOR_DELIVERY],
  [OrderItemStatus.OUT_FOR_DELIVERY]: [OrderItemStatus.DELIVERED],
  [OrderItemStatus.DELIVERED]: [],
  [OrderItemStatus.CANCELLED]: [],
  [OrderItemStatus.RETURNED]: [],
};

// Buyer may cancel only before dispatch
const BUYER_CANCELLABLE = [OrderItemStatus.PLACED, OrderItemStatus.CONFIRMED];

@Injectable()
export class OrderService {
  constructor(
    @InjectRepository(Order)
    private readonly orderRepo: Repository<Order>,
    @InjectRepository(OrderItem)
    private readonly itemRepo: Repository<OrderItem>,
    private readonly dataSource: DataSource,
  ) {}

  // -------- Buyer --------

  async findUserOrders(userId: string, query: PaginationQueryDto) {
    const [items, total] = await this.orderRepo.findAndCount({
      where: { userId },
      relations: ['items'],
      order: { placedAt: 'DESC' },
      skip: query.offset,
      take: query.limit,
    });
    return paginate(items, total, query.page, query.limit, 'Orders fetched');
  }

  async findUserOrder(userId: string, orderId: string): Promise<Order> {
    const order = await this.orderRepo.findOne({
      where: { id: orderId },
      relations: ['items'],
    });
    if (!order) throw new NotFoundException('Order not found');
    if (order.userId !== userId) throw new ForbiddenException('Order not found');
    return order;
  }

  /** Buyer cancels a single item (pre-dispatch); restores stock. */
  async cancelItem(
    userId: string,
    orderItemId: string,
    reason: string,
  ): Promise<OrderItem> {
    return this.dataSource.transaction(async (manager) => {
      const item = await manager.findOne(OrderItem, {
        where: { id: orderItemId },
        relations: ['order'],
      });
      if (!item) throw new NotFoundException('Order item not found');
      if (item.order.userId !== userId) {
        throw new ForbiddenException('Order item not found');
      }
      if (!BUYER_CANCELLABLE.includes(item.status)) {
        throw new BadRequestException(
          `Cannot cancel an item that is already '${item.status}'`,
        );
      }

      // Restore stock
      await manager
        .createQueryBuilder()
        .update(ProductVariant)
        .set({ stockQuantity: () => `"stockQuantity" + ${item.quantity}` })
        .where('id = :id', { id: item.variantId })
        .execute();

      item.status = OrderItemStatus.CANCELLED;
      item.cancelReason = reason;
      const saved = await manager.save(item);
      await this.refreshOrderPayment(manager, item.orderId);
      return saved;
    });
  }

  // -------- Seller --------

  async findSellerItems(sellerId: string, query: PaginationQueryDto) {
    const [items, total] = await this.itemRepo.findAndCount({
      where: { sellerId },
      order: { createdAt: 'DESC' },
      skip: query.offset,
      take: query.limit,
    });
    return paginate(items, total, query.page, query.limit, 'Items fetched');
  }

  async updateItemStatus(
    sellerId: string,
    orderItemId: string,
    nextStatus: OrderItemStatus,
    awbNumber?: string,
  ): Promise<OrderItem> {
    return this.dataSource.transaction(async (manager) => {
      const item = await manager.findOne(OrderItem, {
        where: { id: orderItemId },
      });
      if (!item) throw new NotFoundException('Order item not found');
      if (item.sellerId !== sellerId) {
        throw new ForbiddenException('You do not own this order item');
      }

      const allowed = SELLER_TRANSITIONS[item.status] ?? [];
      if (!allowed.includes(nextStatus)) {
        throw new BadRequestException(
          `Cannot move item from '${item.status}' to '${nextStatus}'`,
        );
      }
      if (nextStatus === OrderItemStatus.SHIPPED && !awbNumber?.trim()) {
        throw new BadRequestException('An AWB number is required when shipping');
      }

      item.status = nextStatus;
      if (awbNumber) item.awbNumber = awbNumber;
      const saved = await manager.save(item);

      // COD: cash is collected on delivery → settle payment when all delivered
      await this.refreshOrderPayment(manager, item.orderId);
      return saved;
    });
  }

  /**
   * Recomputes an order's payment status from its items:
   *  - COD becomes PAID once every non-cancelled item is delivered
   *  - if all items are cancelled, the order is effectively refunded/void
   */
  private async refreshOrderPayment(manager: any, orderId: string) {
    const order = await manager.findOne(Order, {
      where: { id: orderId },
      relations: ['items'],
    });
    if (!order) return;

    const active = order.items.filter(
      (i: OrderItem) => i.status !== OrderItemStatus.CANCELLED,
    );
    if (active.length === 0) {
      order.paymentStatus = PaymentStatus.REFUNDED;
    } else if (
      order.paymentMethod === PaymentMethod.COD &&
      active.every((i: OrderItem) => i.status === OrderItemStatus.DELIVERED)
    ) {
      order.paymentStatus = PaymentStatus.PAID;
    }
    await manager.save(order);
  }
}
