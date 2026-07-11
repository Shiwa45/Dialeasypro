import {
  Injectable,
  Logger,
  NotFoundException,
  ForbiddenException,
  BadRequestException,
} from '@nestjs/common';
import { InjectRepository } from '@nestjs/typeorm';
import { ConfigService } from '@nestjs/config';
import { DataSource, In, Repository } from 'typeorm';
import { Shipment, ShipmentStatus } from '../entities/shipment.entity';
import { Order, PaymentMethod, PaymentStatus } from '../../orders/entities/order.entity';
import {
  OrderItem,
  OrderItemStatus,
} from '../../orders/entities/order-item.entity';
import { ShiprocketService, CourierOption } from './shiprocket.service';
import { UserRole } from '../../users/entities/user.entity';
import { EventEmitter2 } from '@nestjs/event-emitter';
import { NotifyEvents } from '../../notifications/notification.events';

const DEFAULT_ITEM_WEIGHT_G = 500;
const SHIPPABLE = [
  OrderItemStatus.PLACED,
  OrderItemStatus.CONFIRMED,
  OrderItemStatus.PACKED,
];

@Injectable()
export class ShippingService {
  private readonly logger = new Logger('ShippingService');

  constructor(
    @InjectRepository(Shipment)
    private readonly shipmentRepo: Repository<Shipment>,
    @InjectRepository(Order)
    private readonly orderRepo: Repository<Order>,
    private readonly shiprocket: ShiprocketService,
    private readonly config: ConfigService,
    private readonly events: EventEmitter2,
    private readonly dataSource: DataSource,
  ) {}

  /** Courier options for a lane (used at checkout to show delivery estimates). */
  async serviceability(
    deliveryPincode: string,
    weightGrams: number,
    cod: boolean,
  ): Promise<{ pickup: string; couriers: CourierOption[] }> {
    const pickup = this.config.get<string>('shiprocket.pickupPincode')!;
    const couriers = await this.shiprocket.checkServiceability(
      pickup,
      deliveryPincode,
      weightGrams || DEFAULT_ITEM_WEIGHT_G,
      cod,
    );
    return { pickup, couriers };
  }

  /**
   * Creates a courier shipment for one seller's shippable items in an order.
   * Assigns an AWB and moves those items to SHIPPED.
   */
  async createShipment(
    sellerId: string,
    orderId: string,
  ): Promise<Shipment> {
    const order = await this.orderRepo.findOne({
      where: { id: orderId },
      relations: ['items'],
    });
    if (!order) throw new NotFoundException('Order not found');

    // Block shipping if the order is online and not yet paid (clearer than
    // "no shippable items", since unpaid items sit in pending_payment).
    if (
      order.paymentMethod !== PaymentMethod.COD &&
      order.paymentStatus !== PaymentStatus.PAID
    ) {
      throw new BadRequestException('Order payment is not complete');
    }

    const items = order.items.filter(
      (i) => i.sellerId === sellerId && SHIPPABLE.includes(i.status),
    );
    if (items.length === 0) {
      throw new BadRequestException(
        'No shippable items for this seller in this order',
      );
    }

    const addr = order.shippingAddress as Record<string, string>;
    const weightGrams = items.reduce(
      (s, i) => s + DEFAULT_ITEM_WEIGHT_G * i.quantity,
      0,
    );
    const subtotal = items.reduce((s, i) => s + i.lineTotal, 0);

    const created = await this.shiprocket.createShipment({
      orderNumber: `${order.orderNumber}-${sellerId.slice(0, 8)}`,
      pickupPincode: this.config.get<string>('shiprocket.pickupPincode')!,
      delivery: {
        name: addr.name,
        pincode: addr.pincode,
        city: addr.city,
        state: addr.state,
        address: [addr.line1, addr.line2].filter(Boolean).join(', '),
        mobile: addr.mobile,
      },
      items: items.map((i) => ({
        name: i.productTitle,
        sku: i.sku,
        units: i.quantity,
        sellingPrice: i.unitPrice,
      })),
      weightGrams,
      cod: order.paymentMethod === PaymentMethod.COD,
      subTotalPaise: subtotal,
    });

    const shipment = await this.dataSource.transaction(async (manager) => {
      const shipment = manager.create(Shipment, {
        orderId: order.id,
        sellerId,
        providerOrderId: created.providerOrderId,
        providerShipmentId: created.providerShipmentId,
        awbCode: created.awbCode,
        courierName: created.courierName,
        status: ShipmentStatus.AWB_ASSIGNED,
        pickupPincode: this.config.get<string>('shiprocket.pickupPincode')!,
        deliveryPincode: addr.pincode,
        weightGrams,
        labelUrl: created.labelUrl,
        trackingUrl: created.trackingUrl,
        orderItemIds: items.map((i) => i.id),
        trackingEvents: [],
      });
      const saved = await manager.save(shipment);

      // Move covered items to SHIPPED with the AWB
      await manager.update(
        OrderItem,
        { id: In(items.map((i) => i.id)) },
        { status: OrderItemStatus.SHIPPED, awbNumber: created.awbCode },
      );
      return saved;
    });

    this.events.emit(NotifyEvents.ORDER_SHIPPED, {
      orderId: order.id,
      userId: order.userId,
      orderNumber: order.orderNumber,
      awbCode: shipment.awbCode,
      courierName: shipment.courierName,
    });
    return shipment;
  }

  /** Pulls latest tracking and advances shipment + item status. */
  async track(
    shipmentId: string,
    requesterId: string,
    role: UserRole,
  ): Promise<Shipment> {
    const shipment = await this.shipmentRepo.findOne({
      where: { id: shipmentId },
      relations: ['order'],
    });
    if (!shipment) throw new NotFoundException('Shipment not found');
    const isOwnerBuyer = shipment.order.userId === requesterId;
    const isSeller = role === UserRole.SELLER && shipment.sellerId === requesterId;
    if (role !== UserRole.ADMIN && !isOwnerBuyer && !isSeller) {
      throw new ForbiddenException('Not allowed');
    }
    if (!shipment.awbCode) return shipment;

    const { status, events } = await this.shiprocket.track(shipment.awbCode);
    shipment.trackingEvents = events as unknown as Array<
      Record<string, unknown>
    >;
    const mapped = this.mapStatus(status);
    if (mapped) shipment.status = mapped;
    await this.shipmentRepo.save(shipment);

    if (mapped === ShipmentStatus.DELIVERED) {
      await this.markDelivered(shipment);
    }
    return shipment;
  }

  /**
   * Shiprocket tracking webhook. Authenticated by a shared token (the
   * provider includes it in the body/header per the dashboard config).
   */
  async handleWebhook(token: string, payload: any): Promise<void> {
    const expected = this.config.get<string>('shiprocket.webhookToken');
    if (!expected || token !== expected) {
      throw new ForbiddenException('Invalid webhook token');
    }
    const awb = payload?.awb ?? payload?.awb_code;
    const currentStatus = payload?.current_status ?? payload?.shipment_status;
    if (!awb) return;

    const shipment = await this.shipmentRepo.findOne({ where: { awbCode: String(awb) } });
    if (!shipment) return;

    const mapped = this.mapStatus(String(currentStatus));
    if (mapped) {
      shipment.status = mapped;
      await this.shipmentRepo.save(shipment);
      if (mapped === ShipmentStatus.DELIVERED) {
        await this.markDelivered(shipment);
      }
    }
  }

  /** Moves a delivered shipment's items to DELIVERED and settles COD. */
  private async markDelivered(shipment: Shipment): Promise<void> {
    await this.dataSource.transaction(async (manager) => {
      await manager.update(
        OrderItem,
        { id: In(shipment.orderItemIds) },
        { status: OrderItemStatus.DELIVERED },
      );
      const order = await manager.findOne(Order, {
        where: { id: shipment.orderId },
        relations: ['items'],
      });
      if (!order) return;
      const active = order.items.filter(
        (i) => i.status !== OrderItemStatus.CANCELLED,
      );
      if (
        order.paymentMethod === PaymentMethod.COD &&
        active.length > 0 &&
        active.every((i) => i.status === OrderItemStatus.DELIVERED)
      ) {
        order.paymentStatus = PaymentStatus.PAID; // COD cash collected
        await manager.save(order);
      }
    });
    this.logger.log(`Shipment ${shipment.id} delivered`);

    const order = await this.orderRepo.findOne({
      where: { id: shipment.orderId },
    });
    if (order) {
      this.events.emit(NotifyEvents.ORDER_DELIVERED, {
        orderId: order.id,
        userId: order.userId,
        orderNumber: order.orderNumber,
      });
    }
  }

  private mapStatus(srStatus: string): ShipmentStatus | null {
    const s = (srStatus || '').toLowerCase();
    if (s.includes('deliver')) return ShipmentStatus.DELIVERED;
    if (s.includes('out for delivery') || s.includes('out_for_delivery'))
      return ShipmentStatus.OUT_FOR_DELIVERY;
    if (s.includes('transit')) return ShipmentStatus.IN_TRANSIT;
    if (s.includes('pickup')) return ShipmentStatus.PICKUP_SCHEDULED;
    if (s.includes('rto')) return ShipmentStatus.RTO;
    if (s.includes('cancel')) return ShipmentStatus.CANCELLED;
    return null;
  }
}
