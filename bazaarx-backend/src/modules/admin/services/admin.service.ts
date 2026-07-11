import {
  Injectable,
  NotFoundException,
  BadRequestException,
} from '@nestjs/common';
import { InjectRepository } from '@nestjs/typeorm';
import { ILike, Repository } from 'typeorm';
import { User, UserRole } from '../../users/entities/user.entity';
import { Seller, SellerStatus } from '../../sellers/entities/seller.entity';
import { Product, ProductStatus } from '../../catalog/entities/product.entity';
import { Order } from '../../orders/entities/order.entity';
import { OrderItem, OrderItemStatus } from '../../orders/entities/order-item.entity';
import { Review, ReviewStatus } from '../../reviews/entities/review.entity';
import { paginate } from '../../../common/dto/paginated-result';
import { PaginationQueryDto } from '../../../common/dto/pagination-query.dto';

@Injectable()
export class AdminService {
  constructor(
    @InjectRepository(User) private readonly userRepo: Repository<User>,
    @InjectRepository(Seller) private readonly sellerRepo: Repository<Seller>,
    @InjectRepository(Product) private readonly productRepo: Repository<Product>,
    @InjectRepository(Order) private readonly orderRepo: Repository<Order>,
    @InjectRepository(OrderItem) private readonly itemRepo: Repository<OrderItem>,
    @InjectRepository(Review) private readonly reviewRepo: Repository<Review>,
  ) {}

  /** Platform-wide KPIs and the moderation backlog. */
  async overview() {
    const [
      totalUsers,
      totalSellers,
      pendingSellers,
      activeProducts,
      pendingProducts,
      totalOrders,
      pendingReviews,
    ] = await Promise.all([
      this.userRepo.count(),
      this.sellerRepo.count({ where: { status: SellerStatus.APPROVED } }),
      this.sellerRepo.count({ where: { status: SellerStatus.PENDING } }),
      this.productRepo.count({ where: { status: ProductStatus.ACTIVE } }),
      this.productRepo.count({ where: { status: ProductStatus.PENDING_REVIEW } }),
      this.orderRepo.count(),
      this.reviewRepo.count({ where: { status: ReviewStatus.HIDDEN } }),
    ]);

    const gmv = await this.itemRepo
      .createQueryBuilder('i')
      .where('i.status = :s', { s: OrderItemStatus.DELIVERED })
      .select('COALESCE(SUM(i.lineTotal),0)', 'gmv')
      .addSelect('COALESCE(SUM(i.gstAmount),0)', 'gst')
      .getRawOne<{ gmv: string; gst: string }>();

    return {
      users: totalUsers,
      sellers: { approved: totalSellers, pending: pendingSellers },
      products: { active: activeProducts, pendingModeration: pendingProducts },
      orders: totalOrders,
      gmv: Number(gmv?.gmv ?? 0),
      gstCollected: Number(gmv?.gst ?? 0),
      moderationBacklog: {
        sellers: pendingSellers,
        products: pendingProducts,
        hiddenReviews: pendingReviews,
      },
    };
  }

  // -------- User management --------

  async listUsers(query: PaginationQueryDto, search?: string, role?: UserRole) {
    const where: Record<string, unknown> = {};
    if (role) where.role = role;
    if (search) where.mobile = ILike(`%${search}%`);
    const [items, total] = await this.userRepo.findAndCount({
      where,
      order: { createdAt: 'DESC' },
      skip: query.offset,
      take: query.limit,
    });
    return paginate(items, total, query.page, query.limit, 'Users');
  }

  async setUserActive(userId: string, active: boolean): Promise<User> {
    const user = await this.userRepo.findOne({ where: { id: userId } });
    if (!user) throw new NotFoundException('User not found');
    if (user.role === UserRole.ADMIN) {
      throw new BadRequestException('Cannot suspend an admin account');
    }
    user.isActive = active;
    return this.userRepo.save(user);
  }

  async setUserRole(userId: string, role: UserRole): Promise<User> {
    const user = await this.userRepo.findOne({ where: { id: userId } });
    if (!user) throw new NotFoundException('User not found');
    user.role = role;
    return this.userRepo.save(user);
  }

  // -------- Moderation queues --------

  async pendingProducts(query: PaginationQueryDto) {
    const [items, total] = await this.productRepo.findAndCount({
      where: { status: ProductStatus.PENDING_REVIEW },
      order: { createdAt: 'ASC' },
      skip: query.offset,
      take: query.limit,
    });
    return paginate(items, total, query.page, query.limit, 'Pending products');
  }

  async pendingSellers(query: PaginationQueryDto) {
    const [items, total] = await this.sellerRepo.findAndCount({
      where: { status: SellerStatus.PENDING },
      order: { createdAt: 'ASC' },
      skip: query.offset,
      take: query.limit,
    });
    return paginate(items, total, query.page, query.limit, 'Pending sellers');
  }

  async allOrders(query: PaginationQueryDto) {
    const [items, total] = await this.orderRepo.findAndCount({
      relations: ['items'],
      order: { placedAt: 'DESC' },
      skip: query.offset,
      take: query.limit,
    });
    return paginate(items, total, query.page, query.limit, 'All orders');
  }

  // -------- Review moderation --------

  async moderateReview(reviewId: string, hide: boolean): Promise<Review> {
    const review = await this.reviewRepo.findOne({ where: { id: reviewId } });
    if (!review) throw new NotFoundException('Review not found');
    review.status = hide ? ReviewStatus.HIDDEN : ReviewStatus.VISIBLE;
    return this.reviewRepo.save(review);
  }
}
