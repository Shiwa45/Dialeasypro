import {
  Injectable,
  Logger,
  NotFoundException,
  ForbiddenException,
  BadRequestException,
} from '@nestjs/common';
import { InjectRepository } from '@nestjs/typeorm';
import { DataSource, Repository } from 'typeorm';
import { randomBytes } from 'crypto';
import {
  Return,
  ReturnStatus,
  RefundMethod,
} from '../entities/return.entity';
import { Order, PaymentMethod } from '../../orders/entities/order.entity';
import {
  OrderItem,
  OrderItemStatus,
} from '../../orders/entities/order-item.entity';
import { ProductVariant } from '../../catalog/entities/product-variant.entity';
import { PaymentService } from '../../payments/services/payment.service';
import { ShiprocketService } from '../../shipping/services/shiprocket.service';
import { RequestReturnDto } from '../dto/return.dto';
import { paginate } from '../../../common/dto/paginated-result';
import { PaginationQueryDto } from '../../../common/dto/pagination-query.dto';
import { UserRole } from '../../users/entities/user.entity';
import { EventEmitter2 } from '@nestjs/event-emitter';
import { NotifyEvents } from '../../notifications/notification.events';
import { WalletService } from '../../wallet/services/wallet.service';
import { WalletTxnSource } from '../../wallet/entities/wallet.entity';

const RETURN_WINDOW_DAYS = 7;

@Injectable()
export class ReturnService {
  private readonly logger = new Logger('ReturnService');

  constructor(
    @InjectRepository(Return)
    private readonly returnRepo: Repository<Return>,
    @InjectRepository(Order)
    private readonly orderRepo: Repository<Order>,
    @InjectRepository(OrderItem)
    private readonly itemRepo: Repository<OrderItem>,
    private readonly payments: PaymentService,
    private readonly shiprocket: ShiprocketService,
    private readonly wallet: WalletService,
    private readonly events: EventEmitter2,
    private readonly dataSource: DataSource,
  ) {}

  // -------- Buyer --------

  async requestReturn(buyerId: string, dto: RequestReturnDto): Promise<Return> {
    const item = await this.itemRepo.findOne({
      where: { id: dto.orderItemId },
      relations: ['order'],
    });
    if (!item) throw new NotFoundException('Order item not found');
    if (item.order.userId !== buyerId) {
      throw new ForbiddenException('Order item not found');
    }
    if (item.status !== OrderItemStatus.DELIVERED) {
      throw new BadRequestException('Only delivered items can be returned');
    }

    // Return window (uses delivery timestamp proxy = last update to delivered)
    const deliveredAt = item.updatedAt.getTime();
    const ageDays = (Date.now() - deliveredAt) / (1000 * 60 * 60 * 24);
    if (ageDays > RETURN_WINDOW_DAYS) {
      throw new BadRequestException(
        `Return window of ${RETURN_WINDOW_DAYS} days has passed`,
      );
    }

    const existing = await this.returnRepo.findOne({
      where: { orderItemId: item.id },
    });
    if (existing && existing.status !== ReturnStatus.REJECTED) {
      throw new BadRequestException('A return already exists for this item');
    }

    const ret = this.returnRepo.create({
      returnNumber: this.generateReturnNumber(),
      orderId: item.orderId,
      orderItemId: item.id,
      buyerId,
      sellerId: item.sellerId,
      reason: dto.reason,
      comments: dto.comments,
      status: ReturnStatus.REQUESTED,
      refundAmount: item.lineTotal,
    });
    const saved = await this.returnRepo.save(ret);
    this.events.emit(NotifyEvents.RETURN_REQUESTED, {
      returnId: saved.id,
      buyerId: saved.buyerId,
      returnNumber: saved.returnNumber,
    });
    return saved;
  }

  async listForBuyer(buyerId: string, query: PaginationQueryDto) {
    const [items, total] = await this.returnRepo.findAndCount({
      where: { buyerId },
      order: { createdAt: 'DESC' },
      skip: query.offset,
      take: query.limit,
    });
    return paginate(items, total, query.page, query.limit, 'Returns fetched');
  }

  async cancel(buyerId: string, returnId: string): Promise<Return> {
    const ret = await this.findOwned(returnId, buyerId);
    if (![ReturnStatus.REQUESTED, ReturnStatus.APPROVED].includes(ret.status)) {
      throw new BadRequestException('This return can no longer be cancelled');
    }
    ret.status = ReturnStatus.CANCELLED;
    return this.returnRepo.save(ret);
  }

  // -------- Seller / Admin --------

  async listForSeller(sellerId: string, query: PaginationQueryDto) {
    const [items, total] = await this.returnRepo.findAndCount({
      where: { sellerId },
      order: { createdAt: 'DESC' },
      skip: query.offset,
      take: query.limit,
    });
    return paginate(items, total, query.page, query.limit, 'Returns fetched');
  }

  /** Approve a return and create a reverse pickup. */
  async approve(
    actorId: string,
    role: UserRole,
    returnId: string,
  ): Promise<Return> {
    const ret = await this.findForActor(returnId, actorId, role);
    if (ret.status !== ReturnStatus.REQUESTED) {
      throw new BadRequestException('Only requested returns can be approved');
    }

    const order = await this.orderRepo.findOne({ where: { id: ret.orderId } });
    const item = await this.itemRepo.findOne({ where: { id: ret.orderItemId } });
    const addr = (order!.shippingAddress as Record<string, string>) ?? {};

    const reverse = await this.shiprocket.createReturnShipment({
      orderNumber: order!.orderNumber,
      pickup: {
        name: addr.name,
        pincode: addr.pincode,
        city: addr.city,
        state: addr.state,
        address: [addr.line1, addr.line2].filter(Boolean).join(', '),
        mobile: addr.mobile,
      },
      items: [
        {
          name: item!.productTitle,
          sku: item!.sku,
          units: item!.quantity,
          sellingPrice: item!.unitPrice,
        },
      ],
      weightGrams: 500 * item!.quantity,
    });

    ret.status = ReturnStatus.APPROVED;
    ret.reverseAwb = reverse.awbCode;
    const saved = await this.returnRepo.save(ret);
    this.events.emit(NotifyEvents.RETURN_APPROVED, {
      returnId: saved.id,
      buyerId: saved.buyerId,
      returnNumber: saved.returnNumber,
    });
    return saved;
  }

  async reject(
    actorId: string,
    role: UserRole,
    returnId: string,
    reason: string,
  ): Promise<Return> {
    const ret = await this.findForActor(returnId, actorId, role);
    if (ret.status !== ReturnStatus.REQUESTED) {
      throw new BadRequestException('Only requested returns can be rejected');
    }
    ret.status = ReturnStatus.REJECTED;
    ret.rejectionReason = reason;
    return this.returnRepo.save(ret);
  }

  /**
   * Completes a return: marks the item received, issues the refund
   * (Razorpay for prepaid, wallet for COD), restocks, and sets the
   * order item to RETURNED.
   */
  async complete(
    actorId: string,
    role: UserRole,
    returnId: string,
  ): Promise<Return> {
    const ret = await this.findForActor(returnId, actorId, role);
    if (ret.status !== ReturnStatus.APPROVED) {
      throw new BadRequestException(
        'Only approved returns can be completed',
      );
    }

    const order = await this.orderRepo.findOne({ where: { id: ret.orderId } });

    // Issue refund: prepaid → gateway refund; COD → credit store wallet
    let refundMethod: RefundMethod;
    let refundReference: string;
    const gatewayRefund = await this.payments.refund(ret.orderId, ret.refundAmount);
    if (gatewayRefund) {
      refundMethod = RefundMethod.RAZORPAY;
      refundReference = gatewayRefund.refundId;
    } else {
      refundMethod = RefundMethod.WALLET;
      refundReference = ''; // set after crediting the wallet in the txn
    }

    return this.dataSource.transaction(async (manager) => {
      // Credit the buyer's wallet for COD refunds
      if (refundMethod === RefundMethod.WALLET) {
        const txn = await this.wallet.creditTx(
          manager,
          ret.buyerId,
          ret.refundAmount,
          WalletTxnSource.REFUND,
          ret.id,
          `Refund for ${ret.returnNumber}`,
        );
        refundReference = txn.id;
      }

      // Restock the returned units
      const item = await manager.findOne(OrderItem, {
        where: { id: ret.orderItemId },
      });
      if (item) {
        await manager
          .createQueryBuilder()
          .update(ProductVariant)
          .set({ stockQuantity: () => `"stockQuantity" + ${item.quantity}` })
          .where('id = :id', { id: item.variantId })
          .execute();
        item.status = OrderItemStatus.RETURNED;
        await manager.save(item);
      }

      ret.status = ReturnStatus.REFUNDED;
      ret.refundMethod = refundMethod;
      ret.refundReference = refundReference;
      ret.refundedAt = new Date();
      const saved = await manager.save(ret);
      this.logger.log(
        `Return ${ret.returnNumber} refunded ₹${ret.refundAmount / 100} via ${refundMethod}`,
      );
      this.events.emit(NotifyEvents.REFUND_PROCESSED, {
        returnId: saved.id,
        buyerId: saved.buyerId,
        returnNumber: saved.returnNumber,
        refundAmount: saved.refundAmount,
      });
      return saved;
    });
  }

  // -------- helpers --------

  private async findOwned(returnId: string, buyerId: string): Promise<Return> {
    const ret = await this.returnRepo.findOne({ where: { id: returnId } });
    if (!ret) throw new NotFoundException('Return not found');
    if (ret.buyerId !== buyerId) throw new ForbiddenException('Return not found');
    return ret;
  }

  private async findForActor(
    returnId: string,
    actorId: string,
    role: UserRole,
  ): Promise<Return> {
    const ret = await this.returnRepo.findOne({ where: { id: returnId } });
    if (!ret) throw new NotFoundException('Return not found');
    if (role !== UserRole.ADMIN && ret.sellerId !== actorId) {
      throw new ForbiddenException('Not allowed');
    }
    return ret;
  }

  private generateReturnNumber(): string {
    const year = new Date().getFullYear();
    const suffix = randomBytes(4).toString('hex').toUpperCase();
    return `RET-${year}-${suffix}`;
  }
}
