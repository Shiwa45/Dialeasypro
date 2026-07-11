import {
  Inject,
  Injectable,
  NotFoundException,
  BadRequestException,
} from '@nestjs/common';
import { InjectRepository } from '@nestjs/typeorm';
import { In, Repository } from 'typeorm';
import Redis from 'ioredis';
import { REDIS_CLIENT } from '../../database/redis.module';
import { ProductVariant } from '../catalog/entities/product-variant.entity';
import { Product, ProductStatus } from '../catalog/entities/product.entity';

const CART_TTL_SECONDS = 7 * 24 * 60 * 60; // 7 days

/** An enriched cart line returned to the client. */
export interface CartLine {
  variantId: string;
  productId: string;
  productSlug: string;
  title: string;
  attributes: Record<string, string>;
  imageUrl: string | null;
  mrp: number;
  sellingPrice: number;
  quantity: number;
  lineTotal: number;
  availableStock: number;
  inStock: boolean;
  stockWarning: string | null;
}

/**
 * Cart lives in Redis as a hash: cart:<userId> { variantId: quantity }.
 * We persist ONLY variantId + quantity — never prices — so the cart
 * always reflects current pricing and stock when read (enriched from
 * Postgres). This avoids stale-price bugs and supports price-drop UX.
 */
@Injectable()
export class CartService {
  constructor(
    @Inject(REDIS_CLIENT) private readonly redis: Redis,
    @InjectRepository(ProductVariant)
    private readonly variantRepo: Repository<ProductVariant>,
    @InjectRepository(Product)
    private readonly productRepo: Repository<Product>,
  ) {}

  private key(userId: string) {
    return `cart:${userId}`;
  }
  private savedKey(userId: string) {
    return `saved:${userId}`;
  }

  // -------- Read --------

  async getCart(userId: string) {
    const raw = await this.redis.hgetall(this.key(userId));
    return this.buildCart(userId, raw);
  }

  // -------- Mutations --------

  async addItem(userId: string, variantId: string, quantity: number) {
    const variant = await this.loadSellableVariant(variantId);

    const key = this.key(userId);
    const current = parseInt((await this.redis.hget(key, variantId)) || '0', 10);
    const newQty = Math.min(current + quantity, 10);

    if (newQty > variant.stockQuantity) {
      throw new BadRequestException(
        `Only ${variant.stockQuantity} unit(s) available in stock`,
      );
    }

    await this.redis.hset(key, variantId, newQty);
    await this.redis.expire(key, CART_TTL_SECONDS);
    return this.getCart(userId);
  }

  async updateItem(userId: string, variantId: string, quantity: number) {
    const key = this.key(userId);
    const exists = await this.redis.hexists(key, variantId);
    if (!exists) throw new NotFoundException('Item not in cart');

    const variant = await this.loadSellableVariant(variantId);
    if (quantity > variant.stockQuantity) {
      throw new BadRequestException(
        `Only ${variant.stockQuantity} unit(s) available in stock`,
      );
    }

    await this.redis.hset(key, variantId, quantity);
    await this.redis.expire(key, CART_TTL_SECONDS);
    return this.getCart(userId);
  }

  async removeItem(userId: string, variantId: string) {
    await this.redis.hdel(this.key(userId), variantId);
    return this.getCart(userId);
  }

  async clear(userId: string) {
    await this.redis.del(this.key(userId));
    return this.getCart(userId);
  }

  // -------- Save for later --------

  async saveForLater(userId: string, variantId: string) {
    const key = this.key(userId);
    const qty = await this.redis.hget(key, variantId);
    if (!qty) throw new NotFoundException('Item not in cart');
    await this.redis.hdel(key, variantId);
    await this.redis.hset(this.savedKey(userId), variantId, qty);
    await this.redis.expire(this.savedKey(userId), CART_TTL_SECONDS);
    return this.getCart(userId);
  }

  async moveToCart(userId: string, variantId: string) {
    const savedKey = this.savedKey(userId);
    const qty = await this.redis.hget(savedKey, variantId);
    if (!qty) throw new NotFoundException('Item not in saved list');
    await this.redis.hdel(savedKey, variantId);
    return this.addItem(userId, variantId, parseInt(qty, 10));
  }

  async getSaved(userId: string) {
    const raw = await this.redis.hgetall(this.savedKey(userId));
    return this.buildCart(userId, raw);
  }

  // -------- helpers --------

  private async loadSellableVariant(variantId: string): Promise<ProductVariant> {
    const variant = await this.variantRepo.findOne({
      where: { id: variantId },
      relations: ['product'],
    });
    if (!variant || !variant.isActive) {
      throw new NotFoundException('Product variant not available');
    }
    const product = await this.productRepo.findOne({
      where: { id: variant.productId },
    });
    if (!product || product.status !== ProductStatus.ACTIVE) {
      throw new BadRequestException('This product is no longer available');
    }
    return variant;
  }

  /** Turns the Redis hash into an enriched, validated cart with totals. */
  private async buildCart(userId: string, raw: Record<string, string>) {
    const variantIds = Object.keys(raw);
    if (variantIds.length === 0) {
      return { items: [], summary: this.emptySummary() };
    }

    const variants = await this.variantRepo.find({
      where: { id: In(variantIds) },
      relations: ['product'],
    });
    const byId = new Map(variants.map((v) => [v.id, v]));

    const items: CartLine[] = [];
    for (const variantId of variantIds) {
      const variant = byId.get(variantId);
      const quantity = parseInt(raw[variantId], 10);
      // Variant vanished (deleted/unpublished) → prune from cart & skip
      if (!variant || !variant.isActive) {
        await this.redis.hdel(this.key(userId), variantId).catch(() => undefined);
        continue;
      }

      const available = variant.stockQuantity;
      const cappedQty = Math.min(quantity, available);
      items.push({
        variantId: variant.id,
        productId: variant.productId,
        productSlug: variant.product?.slug ?? '',
        title: variant.product?.title ?? '',
        attributes: variant.attributes,
        imageUrl: variant.imageUrls?.[0] ?? null,
        mrp: variant.mrp,
        sellingPrice: variant.sellingPrice,
        quantity,
        lineTotal: variant.sellingPrice * cappedQty,
        availableStock: available,
        inStock: available > 0,
        stockWarning:
          quantity > available
            ? `Only ${available} left; quantity will be adjusted at checkout`
            : null,
      });
    }

    const summary = {
      itemCount: items.length,
      totalQuantity: items.reduce((s, i) => s + i.quantity, 0),
      subtotal: items.reduce((s, i) => s + i.lineTotal, 0),
      totalMrp: items.reduce(
        (s, i) => s + i.mrp * Math.min(i.quantity, i.availableStock),
        0,
      ),
      totalSavings: 0,
    };
    summary.totalSavings = summary.totalMrp - summary.subtotal;

    return { items, summary };
  }

  private emptySummary() {
    return {
      itemCount: 0,
      totalQuantity: 0,
      subtotal: 0,
      totalMrp: 0,
      totalSavings: 0,
    };
  }
}
