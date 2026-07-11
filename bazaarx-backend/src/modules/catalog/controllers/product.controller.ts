import {
  Body,
  Controller,
  Get,
  Post,
  Patch,
  Delete,
  Param,
  Query,
  Version,
  ParseUUIDPipe,
  UseGuards,
  HttpCode,
  HttpStatus,
} from '@nestjs/common';
import { ApiTags, ApiOperation, ApiBearerAuth } from '@nestjs/swagger';
import { ProductService } from '../services/product.service';
import {
  CreateProductDto,
  UpdateProductDto,
  ProductQueryDto,
  ModerateProductDto,
} from '../dto/product.dto';
import { Public } from '../../auth/decorators/public.decorator';
import { Roles } from '../../auth/decorators/roles.decorator';
import { RolesGuard } from '../../auth/guards/roles.guard';
import { CurrentUser } from '../../auth/decorators/current-user.decorator';
import { UserRole } from '../../users/entities/user.entity';

@ApiTags('Catalog · Products')
@Controller('products')
export class ProductController {
  constructor(private readonly products: ProductService) {}

  // -------- Public browsing --------
  @Public()
  @Get()
  @Version('1')
  @ApiOperation({ summary: 'Browse active products (filter, sort, paginate)' })
  browse(@Query() query: ProductQueryDto) {
    return this.products.findPublic(query);
  }

  @Public()
  @Get(':slug')
  @Version('1')
  @ApiOperation({ summary: 'Product detail by slug' })
  async detail(@Param('slug') slug: string) {
    const data = await this.products.findBySlugPublic(slug);
    return { data, message: 'Product fetched' };
  }

  // -------- Seller management --------
  @ApiBearerAuth()
  @UseGuards(RolesGuard)
  @Roles(UserRole.SELLER)
  @Get('seller/mine')
  @Version('1')
  @ApiOperation({ summary: '[Seller] List my products' })
  mine(@CurrentUser('id') sellerId: string, @Query() query: ProductQueryDto) {
    return this.products.findSellerProducts(sellerId, query);
  }

  @ApiBearerAuth()
  @UseGuards(RolesGuard)
  @Roles(UserRole.SELLER)
  @Post()
  @Version('1')
  @ApiOperation({ summary: '[Seller] Create a product (draft)' })
  async create(
    @CurrentUser('id') sellerId: string,
    @Body() dto: CreateProductDto,
  ) {
    const data = await this.products.create(sellerId, dto);
    return { data, message: 'Product created as draft' };
  }

  @ApiBearerAuth()
  @UseGuards(RolesGuard)
  @Roles(UserRole.SELLER)
  @Patch(':id')
  @Version('1')
  @ApiOperation({ summary: '[Seller] Update my product' })
  async update(
    @CurrentUser('id') sellerId: string,
    @Param('id', ParseUUIDPipe) id: string,
    @Body() dto: UpdateProductDto,
  ) {
    const data = await this.products.update(sellerId, id, dto);
    return { data, message: 'Product updated' };
  }

  @ApiBearerAuth()
  @UseGuards(RolesGuard)
  @Roles(UserRole.SELLER)
  @Post(':id/submit')
  @Version('1')
  @HttpCode(HttpStatus.OK)
  @ApiOperation({ summary: '[Seller] Submit product for admin review' })
  async submit(
    @CurrentUser('id') sellerId: string,
    @Param('id', ParseUUIDPipe) id: string,
  ) {
    const data = await this.products.submitForReview(sellerId, id);
    return { data, message: 'Product submitted for review' };
  }

  @ApiBearerAuth()
  @UseGuards(RolesGuard)
  @Roles(UserRole.SELLER, UserRole.ADMIN)
  @Delete(':id')
  @Version('1')
  @ApiOperation({ summary: '[Seller/Admin] Delete a product' })
  async remove(
    @CurrentUser() user: { id: string; role: UserRole },
    @Param('id', ParseUUIDPipe) id: string,
  ) {
    await this.products.remove(user.id, user.role, id);
    return { data: null, message: 'Product deleted' };
  }

  // -------- Admin moderation --------
  @ApiBearerAuth()
  @UseGuards(RolesGuard)
  @Roles(UserRole.ADMIN)
  @Get('admin/pending')
  @Version('1')
  @ApiOperation({ summary: '[Admin] Products awaiting review' })
  pending(@Query() query: ProductQueryDto) {
    return this.products.findPendingReview(query);
  }

  @ApiBearerAuth()
  @UseGuards(RolesGuard)
  @Roles(UserRole.ADMIN)
  @Post(':id/moderate')
  @Version('1')
  @HttpCode(HttpStatus.OK)
  @ApiOperation({ summary: '[Admin] Approve or reject a product' })
  async moderate(
    @Param('id', ParseUUIDPipe) id: string,
    @Body() dto: ModerateProductDto,
  ) {
    const data = await this.products.moderate(id, dto);
    return { data, message: `Product ${dto.status}` };
  }
}
