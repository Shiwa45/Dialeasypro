import { Injectable, Logger } from '@nestjs/common';
import { InjectRepository } from '@nestjs/typeorm';
import { In, Repository } from 'typeorm';
import { ProductVariant } from '../../catalog/entities/product-variant.entity';
import { BecknContextService } from './beckn-context.service';
import { OndcCatalogService } from './ondc-catalog.service';
import { BecknEnvelope } from '../types/beckn.types';

const toRupees = (paise: number) => (paise / 100).toFixed(2);
const DELIVERY = 4000; // ₹40 flat (paise)

interface OrderItemRef {
  id: string;
  quantity: { count: number };
}

/**
 * BazaarX acting as a BPP (seller-side provider) on ONDC. Each protocol
 * action returns its on_* counterpart. In live ONDC the BPP returns an
 * ACK synchronously and POSTs the on_* envelope to the BAP callback URL;
 * this adapter returns the on_* payload directly so the full quote/order
 * shape is testable without the live network.
 */
@Injectable()
export class OndcBppService {
  private readonly logger = new Logger('ONDC-BPP');

  constructor(
    @InjectRepository(ProductVariant)
    private readonly variantRepo: Repository<ProductVariant>,
    private readonly ctx: BecknContextService,
    private readonly catalog: OndcCatalogService,
  ) {}

  async onSearch(env: BecknEnvelope<any>) {
    const text = env.message?.intent?.item?.descriptor?.name as string | undefined;
    const catalog = await this.catalog.buildCatalog(text);
    return {
      context: this.ctx.buildResponseContext(env.context, 'on_search'),
      message: { catalog },
    };
  }

  async onSelect(env: BecknEnvelope<any>) {
    const items: OrderItemRef[] = env.message?.order?.items ?? [];
    const quote = await this.buildQuote(items);
    return {
      context: this.ctx.buildResponseContext(env.context, 'on_select'),
      message: {
        order: {
          provider: env.message?.order?.provider,
          items: env.message?.order?.items,
          quote,
          fulfillments: [
            { id: 'F1', '@ondc/org/provider_name': 'BazaarX', state: { descriptor: { code: 'Serviceable' } } },
          ],
        },
      },
    };
  }

  async onInit(env: BecknEnvelope<any>) {
    const items: OrderItemRef[] = env.message?.order?.items ?? [];
    const quote = await this.buildQuote(items);
    return {
      context: this.ctx.buildResponseContext(env.context, 'on_init'),
      message: {
        order: {
          provider: env.message?.order?.provider,
          items: env.message?.order?.items,
          billing: env.message?.order?.billing,
          fulfillments: env.message?.order?.fulfillments,
          quote,
          payment: {
            type: 'ON-ORDER',
            collected_by: 'BAP',
            '@ondc/org/buyer_app_finder_fee_type': 'percent',
            '@ondc/org/buyer_app_finder_fee_amount': '3',
          },
        },
      },
    };
  }

  async onConfirm(env: BecknEnvelope<any>) {
    const items: OrderItemRef[] = env.message?.order?.items ?? [];
    const quote = await this.buildQuote(items);
    const orderId = env.message?.order?.id ?? `ONDC-${Date.now()}`;
    // Production step: map the ONDC buyer + items to an internal Order via
    // OrderService here. The adapter acknowledges the order shape.
    this.logger.log(`ONDC order confirmed: ${orderId}`);
    return {
      context: this.ctx.buildResponseContext(env.context, 'on_confirm'),
      message: {
        order: {
          id: orderId,
          state: 'Accepted',
          provider: env.message?.order?.provider,
          items: env.message?.order?.items,
          billing: env.message?.order?.billing,
          fulfillments: [
            { id: 'F1', state: { descriptor: { code: 'Pending' } }, type: 'Delivery' },
          ],
          quote,
          payment: env.message?.order?.payment,
          created_at: new Date().toISOString(),
          updated_at: new Date().toISOString(),
        },
      },
    };
  }

  async onStatus(env: BecknEnvelope<any>) {
    const orderId = env.message?.order_id ?? env.message?.order?.id;
    return {
      context: this.ctx.buildResponseContext(env.context, 'on_status'),
      message: {
        order: {
          id: orderId,
          state: 'In-progress',
          fulfillments: [
            {
              id: 'F1',
              type: 'Delivery',
              state: { descriptor: { code: 'Order-picked-up' } },
            },
          ],
          updated_at: new Date().toISOString(),
        },
      },
    };
  }

  /** Builds an ONDC quote (price breakup) for the selected items. */
  private async buildQuote(items: OrderItemRef[]) {
    const ids = items.map((i) => i.id);
    const variants = ids.length
      ? await this.variantRepo.find({ where: { id: In(ids) } })
      : [];
    const priceById = new Map(variants.map((v) => [v.id, v.sellingPrice]));

    let itemsTotal = 0;
    const breakup = items.map((i) => {
      const unit = priceById.get(i.id) ?? 0;
      const count = i.quantity?.count ?? 1;
      const line = unit * count;
      itemsTotal += line;
      return {
        '@ondc/org/item_id': i.id,
        '@ondc/org/item_quantity': { count },
        title: 'item',
        '@ondc/org/title_type': 'item',
        price: { currency: 'INR', value: toRupees(line) },
      };
    });

    breakup.push({
      '@ondc/org/item_id': 'F1',
      '@ondc/org/item_quantity': { count: 1 },
      title: 'Delivery charges',
      '@ondc/org/title_type': 'delivery',
      price: { currency: 'INR', value: toRupees(DELIVERY) },
    } as any);

    return {
      price: { currency: 'INR', value: toRupees(itemsTotal + DELIVERY) },
      breakup,
      ttl: 'P1D',
    };
  }
}
