import {
  Injectable,
  NotFoundException,
  ForbiddenException,
} from '@nestjs/common';
import { InjectRepository } from '@nestjs/typeorm';
import { DataSource, Repository } from 'typeorm';
import { Address } from './entities/address.entity';
import { CreateAddressDto, UpdateAddressDto } from './dto/user.dto';
import { normalizeIndianMobile } from '../../common/decorators/is-indian-mobile.decorator';

/**
 * Manages a user's saved addresses with one invariant:
 * exactly one address can be the default at a time.
 */
@Injectable()
export class AddressService {
  constructor(
    @InjectRepository(Address)
    private readonly addressRepo: Repository<Address>,
    private readonly dataSource: DataSource,
  ) {}

  findAllForUser(userId: string): Promise<Address[]> {
    return this.addressRepo.find({
      where: { userId },
      order: { isDefault: 'DESC', updatedAt: 'DESC' },
    });
  }

  async findOneForUser(userId: string, id: string): Promise<Address> {
    const address = await this.addressRepo.findOne({ where: { id } });
    if (!address) throw new NotFoundException('Address not found');
    if (address.userId !== userId) {
      // Don't reveal existence of someone else's address
      throw new ForbiddenException('Address not found');
    }
    return address;
  }

  async create(userId: string, dto: CreateAddressDto): Promise<Address> {
    const count = await this.addressRepo.count({ where: { userId } });
    // First address is always default; otherwise honour the flag
    const makeDefault = count === 0 ? true : !!dto.isDefault;

    return this.dataSource.transaction(async (manager) => {
      if (makeDefault) {
        await manager.update(Address, { userId }, { isDefault: false });
      }
      const address = manager.create(Address, {
        ...dto,
        mobile: normalizeIndianMobile(dto.mobile),
        userId,
        isDefault: makeDefault,
      });
      return manager.save(address);
    });
  }

  async update(
    userId: string,
    id: string,
    dto: UpdateAddressDto,
  ): Promise<Address> {
    const address = await this.findOneForUser(userId, id);

    return this.dataSource.transaction(async (manager) => {
      // Promoting this one to default → demote the others
      if (dto.isDefault === true && !address.isDefault) {
        await manager.update(Address, { userId }, { isDefault: false });
      }
      Object.assign(address, {
        ...dto,
        mobile: dto.mobile
          ? normalizeIndianMobile(dto.mobile)
          : address.mobile,
      });
      return manager.save(address);
    });
  }

  async setDefault(userId: string, id: string): Promise<Address> {
    const address = await this.findOneForUser(userId, id);
    return this.dataSource.transaction(async (manager) => {
      await manager.update(Address, { userId }, { isDefault: false });
      address.isDefault = true;
      return manager.save(address);
    });
  }

  async remove(userId: string, id: string): Promise<void> {
    const address = await this.findOneForUser(userId, id);
    const wasDefault = address.isDefault;
    await this.addressRepo.softRemove(address);

    // If we removed the default, promote the most recent remaining one
    if (wasDefault) {
      const next = await this.addressRepo.findOne({
        where: { userId },
        order: { updatedAt: 'DESC' },
      });
      if (next) {
        next.isDefault = true;
        await this.addressRepo.save(next);
      }
    }
  }
}
