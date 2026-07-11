import {
  Body,
  Controller,
  Get,
  Post,
  Patch,
  Delete,
  Param,
  Version,
  ParseUUIDPipe,
  UseGuards,
} from '@nestjs/common';
import { ApiTags, ApiOperation, ApiBearerAuth } from '@nestjs/swagger';
import { CategoryService } from '../services/category.service';
import { CreateCategoryDto, UpdateCategoryDto } from '../dto/category.dto';
import { Public } from '../../auth/decorators/public.decorator';
import { Roles } from '../../auth/decorators/roles.decorator';
import { RolesGuard } from '../../auth/guards/roles.guard';
import { UserRole } from '../../users/entities/user.entity';

@ApiTags('Catalog · Categories')
@Controller('categories')
export class CategoryController {
  constructor(private readonly categories: CategoryService) {}

  // ---- Public ----
  @Public()
  @Get('tree')
  @Version('1')
  @ApiOperation({ summary: 'Full active category tree (nested)' })
  async tree() {
    const data = await this.categories.findTree();
    return { data, message: 'Category tree fetched' };
  }

  @Public()
  @Get(':slug')
  @Version('1')
  @ApiOperation({ summary: 'Get a category by slug' })
  async bySlug(@Param('slug') slug: string) {
    const data = await this.categories.findBySlug(slug);
    return { data, message: 'Category fetched' };
  }

  @Public()
  @Get(':id/children')
  @Version('1')
  @ApiOperation({ summary: 'Direct subcategories of a category' })
  async children(@Param('id', ParseUUIDPipe) id: string) {
    const data = await this.categories.findChildren(id);
    return { data, message: 'Subcategories fetched' };
  }

  // ---- Admin ----
  @ApiBearerAuth()
  @UseGuards(RolesGuard)
  @Roles(UserRole.ADMIN)
  @Post()
  @Version('1')
  @ApiOperation({ summary: '[Admin] Create a category' })
  async create(@Body() dto: CreateCategoryDto) {
    const data = await this.categories.create(dto);
    return { data, message: 'Category created' };
  }

  @ApiBearerAuth()
  @UseGuards(RolesGuard)
  @Roles(UserRole.ADMIN)
  @Patch(':id')
  @Version('1')
  @ApiOperation({ summary: '[Admin] Update a category' })
  async update(
    @Param('id', ParseUUIDPipe) id: string,
    @Body() dto: UpdateCategoryDto,
  ) {
    const data = await this.categories.update(id, dto);
    return { data, message: 'Category updated' };
  }

  @ApiBearerAuth()
  @UseGuards(RolesGuard)
  @Roles(UserRole.ADMIN)
  @Delete(':id')
  @Version('1')
  @ApiOperation({ summary: '[Admin] Delete a category' })
  async remove(@Param('id', ParseUUIDPipe) id: string) {
    await this.categories.remove(id);
    return { data: null, message: 'Category deleted' };
  }
}
