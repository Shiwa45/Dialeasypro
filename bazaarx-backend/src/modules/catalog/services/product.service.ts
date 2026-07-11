import {
  Injectable,
  NotFoundException,
  ForbiddenException,
  BadRequestException,
} from '@nestjs/common';
import { InjectRepository } from '@nestjs/typeorm';
import { DataSource, Repository } from 'typeorm';
import { EventEmitter2 } from '@nestjs/event-emitter';
import { Product, ProductStatus } from '../entities/product.entity';
import { ProductVariant } from '../entities/product-variant.entity';
import { Category } from '../entities/category.entity';
import {
  CreateProductDto,
  UpdateProductDto,
  ProductQueryDto,
  ModerateProductDto,
} from '../dto/product.dto';
import { paginate } from '../../../common/dto/paginated-result';
import { slugify } from '../../../common/utils/slug.util';
import { UserRole } from '../../users/entities/user.entity';
import { ProductEvents } from '../product.events';

@Injectable()
export class ProductService {
  constructor(
    @InjectRepository(Product)
    private readonly productRepo: Repository<Product>,
    @InjectRepository(Category)
    private readonly categoryRepo: Repository<Category>,
    private readonly dataSource: DataSource,
    private readonly events: EventEmitter2,
  ) {}

  // -------- Seller operations --------

  async create(sellerId: string, dto: CreateProductDto): Promise<Product> {
    const category = await this.categoryRepo.findOne({
      where: { id: dto.categoryId },
    });
    if (!category) throw new NotFoundException('Category not found');
    if (!dto.variants?.length) {
      throw new BadRequestException('A product needs at least one variant');
    }
    this.assertVariantPricing(dto);
    await this.assertUniqueSkus(dto.variants.map((v) => v.sku));

    return this.dataSource.transaction(async (manager) => {
      const product = manager.create(Product, {
        sellerId,
        categoryId: dto.categoryId,
        brandId: dto.brandId,
        title: dto.title,
        hsnCode: dto.hsnCode ?? '9999',
        slug: await this.uniqueSlug(dto.title, manager.getRepository(Product)),
        description: dto.description,
        highlights: dto.highlights ?? [],
        specifications: dto.specifications ?? {},
        tags: dto.tags ?? [],
        status: ProductStatus.DRAFT,
        metaTitle: dto.title,
      });
      const saved = await manager.save(product);

      const variants = dto.variants.map((v) =>
        manager.create(ProductVariant, { ...v, productId: saved.id }),
      );
      await manager.save(variants);
      saved.variants = variants;
      return saved;
    });
  }

  async findSellerProducts(sellerId: string, query: ProductQueryDto) {
    const qb = this.productRepo
      .createQueryBuilder('p')
      .leftJoinAndSelect('p.variants', 'v')
      .where('p.sellerId = :sellerId', { sellerId });

    if (query.categoryId)
      qb.andWhere('p.categoryId = :cid', { cid: query.categoryId });

    qb.orderBy('p.createdAt', 'DESC')
      .skip(query.offset)
      .take(query.limit);

    const [items, total] = await qb.getManyAndCount();
    return paginate(items, total, query.page, query.limit, 'Products fetched');
  }

  async submitForReview(sellerId: string, id: string): Promise<Product> {
    const product = await this.findOwned(sellerId, id);
    if (
      product.status !== ProductStatus.DRAFT &&
      product.status !== ProductStatus.REJECTED
    ) {
      throw new BadRequestException(
        `Cannot submit a product in '${product.status}' state`,
      );
    }
    product.status = ProductStatus.PENDING_REVIEW;
    product.rejectionReason = undefined;
    return this.productRepo.save(product);
  }

  async update(
    sellerId: string,
    id: string,
    dto: UpdateProductDto,
  ): Promise<Product> {
    const product = await this.findOwned(sellerId, id);
    if (dto.categoryId) {
      const cat = await this.categoryRepo.findOne({
        where: { id: dto.categoryId },
      });
      if (!cat) throw new NotFoundException('Category not found');
    }
    // Editing non-variant fields here; variants managed via dedicated endpoints
    const { variants, ...rest } = dto;
    Object.assign(product, rest);
    return this.productRepo.save(product);
  }

  async remove(
    userId: string,
    role: UserRole,
    id: string,
  ): Promise<void> {
    const product = await this.productRepo.findOne({ where: { id } });
    if (!product) throw new NotFoundException('Product not found');
    if (role !== UserRole.ADMIN && product.sellerId !== userId) {
      throw new ForbiddenException('You do not own this product');
    }
    await this.productRepo.softRemove(product);
    this.events.emit(ProductEvents.UNPUBLISHED, { productId: id });
  }

  // -------- Admin moderation --------

  async moderate(id: string, dto: ModerateProductDto): Promise<Product> {
    const product = await this.productRepo.findOne({ where: { id } });
    if (!product) throw new NotFoundException('Product not found');
    if (product.status !== ProductStatus.PENDING_REVIEW) {
      throw new BadRequestException('Product is not awaiting review');
    }
    if (
      dto.status === ProductStatus.REJECTED &&
      !dto.rejectionReason?.trim()
    ) {
      throw new BadRequestException('A rejection reason is required');
    }
    product.status = dto.status;
    product.rejectionReason =
      dto.status === ProductStatus.REJECTED ? dto.rejectionReason : undefined;
    const saved = await this.productRepo.save(product);

    // Sync the search index
    if (dto.status === ProductStatus.ACTIVE) {
      this.events.emit(ProductEvents.PUBLISHED, { productId: saved.id });
    } else {
      this.events.emit(ProductEvents.UNPUBLISHED, { productId: saved.id });
    }
    return saved;
  }

  async findPendingReview(query: ProductQueryDto) {
    const [items, total] = await this.productRepo.findAndCount({
      where: { status: ProductStatus.PENDING_REVIEW },
      relations: ['variants'],
      order: { createdAt: 'ASC' },
      skip: query.offset,
      take: query.limit,
    });
    return paginate(items, total, query.page, query.limit, 'Pending products');
  }

  // -------- Public browsing --------

  async findPublic(query: ProductQueryDto) {
    const qb = this.productRepo
      .createQueryBuilder('p')
      .leftJoinAndSelect('p.variants', 'v')
      .leftJoinAndSelect('p.brand', 'b')
      .where('p.status = :status', { status: ProductStatus.ACTIVE });

    if (query.categoryId)
      qb.andWhere('p.categoryId = :cid', { cid: query.categoryId });
    if (query.brandId)
      qb.andWhere('p.brandId = :bid', { bid: query.brandId });
    if (query.search)
      qb.andWhere('p.title ILIKE :s', { s: `%${query.search}%` });
    if (query.minPrice != null)
      qb.andWhere('v.sellingPrice >= :min', { min: query.minPrice });
    if (query.maxPrice != null)
      qb.andWhere('v.sellingPrice <= :max', { max: query.maxPrice });

    const sortable: Record<string, string> = {
      price: 'v.sellingPrice',
      rating: 'p.avgRating',
      newest: 'p.createdAt',
    };
    const sortCol = sortable[query.sortBy ?? 'newest'] ?? 'p.createdAt';
    qb.orderBy(sortCol, query.sortOrder).skip(query.offset).take(query.limit);

    const [items, total] = await qb.getManyAndCount();
    return paginate(items, total, query.page, query.limit, 'Products fetched');
  }

  async findBySlugPublic(slug: string): Promise<Product> {
    const product = await this.productRepo.findOne({
      where: { slug, status: ProductStatus.ACTIVE },
      relations: ['variants', 'brand', 'category'],
    });
    if (!product) throw new NotFoundException('Product not found');
    return product;
  }

  // -------- helpers --------

  private async findOwned(sellerId: string, id: string): Promise<Product> {
    const product = await this.productRepo.findOne({
      where: { id },
      relations: ['variants'],
    });
    if (!product) throw new NotFoundException('Product not found');
    if (product.sellerId !== sellerId) {
      throw new ForbiddenException('You do not own this product');
    }
    return product;
  }

  private assertVariantPricing(dto: CreateProductDto) {
    for (const v of dto.variants) {
      if (v.sellingPrice > v.mrp) {
        throw new BadRequestException(
          `Variant ${v.sku}: selling price cannot exceed MRP`,
        );
      }
    }
  }

  private async assertUniqueSkus(skus: string[]): Promise<void> {
    const dupes = skus.filter((s, i) => skus.indexOf(s) !== i);
    if (dupes.length) {
      throw new BadRequestException(`Duplicate SKUs in request: ${dupes.join(', ')}`);
    }
    const existing = await this.dataSource
      .getRepository(ProductVariant)
      .createQueryBuilder('v')
      .where('v.sku IN (:...skus)', { skus })
      .getCount();
    if (existing > 0) {
      throw new BadRequestException('One or more SKUs already exist');
    }
  }

  private async uniqueSlug(
    title: string,
    repo: Repository<Product>,
  ): Promise<string> {
    const base = slugify(title);
    let slug = base;
    let n = 1;
    while (await repo.exists({ where: { slug } })) {
      slug = `${base}-${n++}`;
    }
    return slug;
  }
}
