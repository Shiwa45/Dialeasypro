import { Injectable } from '@nestjs/common';
import { InjectRepository } from '@nestjs/typeorm';
import { Repository, ILike } from 'typeorm';
import { ConfigService } from '@nestjs/config';
import { Product, ProductStatus } from '../../catalog/entities/product.entity';

/** paise → ONDC decimal-rupee string, e.g. 50000 → "500.00" */
const toRupees = (paise: number) => (paise / 100).toFixed(2);

/**
 * Maps the BazaarX catalogue into ONDC (Beckn) catalog structures used
 * in on_search responses: a provider with locations, items, fulfillments,
 * and price tags.
 */
@Injectable()
export class OndcCatalogService {
  constructor(
    @InjectRepository(Product)
    private readonly productRepo: Repository<Product>,
    private readonly config: ConfigService,
  ) {}

  /** Builds the `catalog` block of an on_search message. */
  async buildCatalog(searchText?: string) {
    const where: Record<string, unknown> = { status: ProductStatus.ACTIVE };
    if (searchText) where.title = ILike(`%${searchText}%`);
    const products = await this.productRepo.find({
      where,
      relations: ['variants'],
      take: 50,
    });

    const items = products.flatMap((p) =>
      (p.variants ?? [])
        .filter((v) => v.isActive)
        .map((v) => ({
          id: v.id,
          descriptor: {
            name: p.title,
            code: v.sku,
            images: v.imageUrls ?? [],
          },
          price: {
            currency: 'INR',
            value: toRupees(v.sellingPrice),
            maximum_value: toRupees(v.mrp),
          },
          category_id: p.categoryId,
          fulfillment_id: 'F1',
          location_id: 'L1',
          '@ondc/org/available_on_cod': true,
          '@ondc/org/returnable': true,
          '@ondc/org/seller_pickup_return': true,
          '@ondc/org/return_window': 'P7D',
          quantity: {
            available: { count: v.stockQuantity > 0 ? '99' : '0' },
            maximum: { count: '10' },
          },
        })),
    );

    return {
      'bpp/descriptor': { name: 'BazaarX' },
      'bpp/providers': [
        {
          id: this.config.get<string>('ondc.subscriberId'),
          descriptor: { name: 'BazaarX Marketplace' },
          locations: [
            {
              id: 'L1',
              gps: '12.9716,77.5946',
              address: { city: 'Bengaluru', state: 'Karnataka' },
            },
          ],
          fulfillments: [{ id: 'F1', type: 'Delivery' }],
          items,
        },
      ],
    };
  }
}
