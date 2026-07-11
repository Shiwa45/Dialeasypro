import {
  Injectable,
  NotFoundException,
  ConflictException,
  BadRequestException,
} from '@nestjs/common';
import { InjectRepository } from '@nestjs/typeorm';
import { DataSource, Repository } from 'typeorm';
import { Seller, SellerStatus } from '../entities/seller.entity';
import { SellerDocument } from '../entities/seller-document.entity';
import {
  RegisterSellerDto,
  UpdateSellerDto,
} from '../dto/seller.dto';
import { UsersService } from '../../users/users.service';
import { UserRole } from '../../users/entities/user.entity';
import { paginate } from '../../../common/dto/paginated-result';
import { PaginationQueryDto } from '../../../common/dto/pagination-query.dto';

@Injectable()
export class SellerService {
  constructor(
    @InjectRepository(Seller)
    private readonly sellerRepo: Repository<Seller>,
    private readonly users: UsersService,
    private readonly dataSource: DataSource,
  ) {}

  // -------- Applicant (any logged-in user) --------

  async register(userId: string, dto: RegisterSellerDto): Promise<Seller> {
    const existing = await this.sellerRepo.findOne({ where: { userId } });
    if (existing) {
      throw new ConflictException(
        `You already have a seller application (${existing.status})`,
      );
    }
    const gstTaken = await this.sellerRepo.findOne({
      where: { gstin: dto.gstin.toUpperCase() },
    });
    if (gstTaken) throw new ConflictException('This GSTIN is already registered');

    return this.dataSource.transaction(async (manager) => {
      const seller = manager.create(Seller, {
        userId,
        displayName: dto.displayName,
        businessName: dto.businessName,
        businessType: dto.businessType,
        gstin: dto.gstin.toUpperCase(),
        pan: dto.pan.toUpperCase(),
        bankAccountHolder: dto.bankAccountHolder,
        bankAccountNumber: dto.bankAccountNumber,
        bankIfsc: dto.bankIfsc.toUpperCase(),
        status: SellerStatus.PENDING,
      });
      const saved = await manager.save(seller);

      const docs = dto.documents.map((d) =>
        manager.create(SellerDocument, { ...d, sellerId: saved.id }),
      );
      await manager.save(docs);
      saved.documents = docs;
      return saved;
    });
  }

  async getMine(userId: string): Promise<Seller> {
    const seller = await this.sellerRepo.findOne({
      where: { userId },
      relations: ['documents'],
    });
    if (!seller) throw new NotFoundException('No seller application found');
    return seller;
  }

  async updateMine(userId: string, dto: UpdateSellerDto): Promise<Seller> {
    const seller = await this.getMine(userId);
    if (dto.bankIfsc) dto.bankIfsc = dto.bankIfsc.toUpperCase();
    Object.assign(seller, dto);
    return this.sellerRepo.save(seller);
  }

  // -------- Admin --------

  async findByStatus(status: SellerStatus, query: PaginationQueryDto) {
    const [items, total] = await this.sellerRepo.findAndCount({
      where: { status },
      relations: ['documents'],
      order: { createdAt: 'ASC' },
      skip: query.offset,
      take: query.limit,
    });
    return paginate(items, total, query.page, query.limit, 'Sellers fetched');
  }

  async approve(sellerId: string, adminId: string): Promise<Seller> {
    const seller = await this.findOne(sellerId);
    if (seller.status === SellerStatus.APPROVED) {
      throw new BadRequestException('Seller is already approved');
    }

    return this.dataSource.transaction(async (manager) => {
      seller.status = SellerStatus.APPROVED;
      seller.approvedAt = new Date();
      seller.approvedByAdminId = adminId;
      seller.rejectionReason = undefined;
      const saved = await manager.save(seller);

      // Promote the user to SELLER so they can list products
      await manager.update(
        'users',
        { id: seller.userId },
        { role: UserRole.SELLER },
      );
      return saved;
    });
  }

  async reject(sellerId: string, reason: string): Promise<Seller> {
    const seller = await this.findOne(sellerId);
    seller.status = SellerStatus.REJECTED;
    seller.rejectionReason = reason;
    return this.sellerRepo.save(seller);
  }

  async suspend(sellerId: string, reason: string): Promise<Seller> {
    const seller = await this.findOne(sellerId);
    seller.status = SellerStatus.SUSPENDED;
    seller.rejectionReason = reason;
    // Optionally demote role back to buyer to block new listings
    await this.users.setRole(seller.userId, UserRole.BUYER);
    return this.sellerRepo.save(seller);
  }

  async findOne(id: string): Promise<Seller> {
    const seller = await this.sellerRepo.findOne({
      where: { id },
      relations: ['documents'],
    });
    if (!seller) throw new NotFoundException('Seller not found');
    return seller;
  }
}
