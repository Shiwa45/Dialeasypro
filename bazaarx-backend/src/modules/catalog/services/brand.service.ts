import { Injectable, NotFoundException } from '@nestjs/common';
import { InjectRepository } from '@nestjs/typeorm';
import { Repository } from 'typeorm';
import { Brand } from '../entities/brand.entity';
import { CreateBrandDto, UpdateBrandDto } from '../dto/product.dto';
import { slugify } from '../../../common/utils/slug.util';

@Injectable()
export class BrandService {
  constructor(
    @InjectRepository(Brand)
    private readonly repo: Repository<Brand>,
  ) {}

  async create(dto: CreateBrandDto): Promise<Brand> {
    const brand = this.repo.create({
      ...dto,
      slug: await this.uniqueSlug(dto.name),
    });
    return this.repo.save(brand);
  }

  findAll(): Promise<Brand[]> {
    return this.repo.find({
      where: { isActive: true },
      order: { name: 'ASC' },
    });
  }

  async findOne(id: string): Promise<Brand> {
    const brand = await this.repo.findOne({ where: { id } });
    if (!brand) throw new NotFoundException('Brand not found');
    return brand;
  }

  async update(id: string, dto: UpdateBrandDto): Promise<Brand> {
    const brand = await this.findOne(id);
    if (dto.name && dto.name !== brand.name) {
      brand.slug = await this.uniqueSlug(dto.name);
    }
    Object.assign(brand, dto);
    return this.repo.save(brand);
  }

  async remove(id: string): Promise<void> {
    const brand = await this.findOne(id);
    await this.repo.softRemove(brand);
  }

  private async uniqueSlug(name: string): Promise<string> {
    const base = slugify(name);
    let slug = base;
    let n = 1;
    while (await this.repo.exists({ where: { slug } })) {
      slug = `${base}-${n++}`;
    }
    return slug;
  }
}
