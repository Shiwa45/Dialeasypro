import {
  Injectable,
  NotFoundException,
  BadRequestException,
} from '@nestjs/common';
import { InjectRepository } from '@nestjs/typeorm';
import { Repository, IsNull } from 'typeorm';
import { Category } from '../entities/category.entity';
import { CreateCategoryDto, UpdateCategoryDto } from '../dto/category.dto';
import { slugify } from '../../../common/utils/slug.util';

const MAX_DEPTH = 2; // 0,1,2 → three levels

@Injectable()
export class CategoryService {
  constructor(
    @InjectRepository(Category)
    private readonly repo: Repository<Category>,
  ) {}

  async create(dto: CreateCategoryDto): Promise<Category> {
    let level = 0;

    if (dto.parentId) {
      const parent = await this.repo.findOne({ where: { id: dto.parentId } });
      if (!parent) throw new NotFoundException('Parent category not found');
      if (parent.level >= MAX_DEPTH) {
        throw new BadRequestException(
          `Category hierarchy cannot exceed ${MAX_DEPTH + 1} levels`,
        );
      }
      level = parent.level + 1;
    }

    const category = this.repo.create({
      ...dto,
      level,
      slug: await this.uniqueSlug(dto.name),
    });
    return this.repo.save(category);
  }

  /** Returns the full active category tree (nested children). */
  async findTree(): Promise<Category[]> {
    const all = await this.repo.find({
      where: { isActive: true },
      order: { sortOrder: 'ASC', name: 'ASC' },
    });
    return this.buildTree(all);
  }

  /** Flat list of root categories only. */
  findRoots(): Promise<Category[]> {
    return this.repo.find({
      where: { parentId: IsNull(), isActive: true },
      order: { sortOrder: 'ASC' },
    });
  }

  async findOne(id: string): Promise<Category> {
    const category = await this.repo.findOne({ where: { id } });
    if (!category) throw new NotFoundException('Category not found');
    return category;
  }

  async findBySlug(slug: string): Promise<Category> {
    const category = await this.repo.findOne({ where: { slug } });
    if (!category) throw new NotFoundException('Category not found');
    return category;
  }

  /** Direct children of a category. */
  findChildren(parentId: string): Promise<Category[]> {
    return this.repo.find({
      where: { parentId, isActive: true },
      order: { sortOrder: 'ASC' },
    });
  }

  async update(id: string, dto: UpdateCategoryDto): Promise<Category> {
    const category = await this.findOne(id);
    // Renaming regenerates slug only if name actually changed
    if (dto.name && dto.name !== category.name) {
      category.slug = await this.uniqueSlug(dto.name);
    }
    Object.assign(category, dto);
    return this.repo.save(category);
  }

  async remove(id: string): Promise<void> {
    const category = await this.findOne(id);
    const childCount = await this.repo.count({ where: { parentId: id } });
    if (childCount > 0) {
      throw new BadRequestException(
        'Cannot delete a category that has subcategories',
      );
    }
    await this.repo.softRemove(category);
  }

  // ---- helpers ----

  private buildTree(categories: Category[]): Category[] {
    const byId = new Map<string, Category & { children: Category[] }>();
    categories.forEach((c) => byId.set(c.id, { ...c, children: [] }));

    const roots: Category[] = [];
    byId.forEach((node) => {
      if (node.parentId && byId.has(node.parentId)) {
        byId.get(node.parentId)!.children.push(node);
      } else {
        roots.push(node);
      }
    });
    return roots;
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
