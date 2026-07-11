import { Inject, Injectable, Logger } from '@nestjs/common';
import { InjectRepository } from '@nestjs/typeorm';
import { Repository } from 'typeorm';
import { Client as EsClient } from '@elastic/elasticsearch';
import { ES_CLIENT } from '../../../database/elasticsearch.module';
import { Product, ProductStatus } from '../../catalog/entities/product.entity';
import {
  PRODUCT_INDEX,
  productIndexSettings,
  ProductDocument,
} from '../search.config';

/**
 * Keeps the Elasticsearch products index in sync with Postgres.
 * Only ACTIVE products are indexed (buyers can only find live listings).
 */
@Injectable()
export class ProductIndexService {
  private readonly logger = new Logger('ProductIndex');

  constructor(
    @Inject(ES_CLIENT) private readonly es: EsClient,
    @InjectRepository(Product)
    private readonly productRepo: Repository<Product>,
  ) {}

  /** Creates the index with mappings if it doesn't already exist. */
  async ensureIndex(): Promise<void> {
    const exists = await this.es.indices.exists({ index: PRODUCT_INDEX });
    if (!exists) {
      await this.es.indices.create({
        index: PRODUCT_INDEX,
        ...productIndexSettings,
      });
      this.logger.log(`Created ES index '${PRODUCT_INDEX}'`);
    }
  }

  /** Indexes (or re-indexes) a single product by id. */
  async indexProduct(productId: string): Promise<void> {
    const product = await this.productRepo.findOne({
      where: { id: productId },
      relations: ['variants', 'brand', 'category'],
    });
    if (!product) return;

    // Only active products belong in the searchable index
    if (product.status !== ProductStatus.ACTIVE) {
      await this.removeProduct(productId);
      return;
    }

    const doc = this.toDocument(product);
    await this.es.index({
      index: PRODUCT_INDEX,
      id: product.id,
      document: doc,
      refresh: 'wait_for', // make it searchable immediately
    });
  }

  /** Removes a product from the index (unpublished/deleted/rejected). */
  async removeProduct(productId: string): Promise<void> {
    try {
      await this.es.delete({
        index: PRODUCT_INDEX,
        id: productId,
        refresh: 'wait_for',
      });
    } catch (err: any) {
      // 404 = already absent, which is fine
      if (err?.meta?.statusCode !== 404) throw err;
    }
  }

  /** Rebuilds the entire index from Postgres (admin/recovery). */
  async reindexAll(): Promise<{ indexed: number }> {
    await this.recreateIndex();

    const batchSize = 500;
    let offset = 0;
    let indexed = 0;

    for (;;) {
      const products = await this.productRepo.find({
        where: { status: ProductStatus.ACTIVE },
        relations: ['variants', 'brand', 'category'],
        take: batchSize,
        skip: offset,
        order: { createdAt: 'ASC' },
      });
      if (products.length === 0) break;

      const operations = products.flatMap((p) => [
        { index: { _index: PRODUCT_INDEX, _id: p.id } },
        this.toDocument(p),
      ]);
      await this.es.bulk({ operations, refresh: false });

      indexed += products.length;
      offset += batchSize;
    }

    await this.es.indices.refresh({ index: PRODUCT_INDEX });
    this.logger.log(`Reindexed ${indexed} products`);
    return { indexed };
  }

  private async recreateIndex(): Promise<void> {
    const exists = await this.es.indices.exists({ index: PRODUCT_INDEX });
    if (exists) await this.es.indices.delete({ index: PRODUCT_INDEX });
    await this.es.indices.create({
      index: PRODUCT_INDEX,
      ...productIndexSettings,
    });
  }

  private toDocument(product: Product): ProductDocument {
    const prices = (product.variants ?? [])
      .filter((v) => v.isActive)
      .map((v) => v.sellingPrice);
    const totalStock = (product.variants ?? []).reduce(
      (sum, v) => sum + v.stockQuantity,
      0,
    );

    return {
      id: product.id,
      sellerId: product.sellerId,
      title: product.title,
      description: product.description,
      highlights: product.highlights ?? [],
      tags: product.tags ?? [],
      categoryId: product.categoryId,
      categoryName: product.category?.name ?? '',
      brandId: product.brandId,
      brandName: product.brand?.name,
      minPrice: prices.length ? Math.min(...prices) : 0,
      maxPrice: prices.length ? Math.max(...prices) : 0,
      avgRating: Number(product.avgRating),
      reviewCount: product.reviewCount,
      inStock: totalStock > 0,
      createdAt: product.createdAt.toISOString(),
    };
  }
}
