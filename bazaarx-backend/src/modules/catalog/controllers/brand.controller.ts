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
import { BrandService } from '../services/brand.service';
import { CreateBrandDto, UpdateBrandDto } from '../dto/product.dto';
import { Public } from '../../auth/decorators/public.decorator';
import { Roles } from '../../auth/decorators/roles.decorator';
import { RolesGuard } from '../../auth/guards/roles.guard';
import { UserRole } from '../../users/entities/user.entity';

@ApiTags('Catalog · Brands')
@Controller('brands')
export class BrandController {
  constructor(private readonly brands: BrandService) {}

  @Public()
  @Get()
  @Version('1')
  @ApiOperation({ summary: 'List all active brands' })
  async list() {
    const data = await this.brands.findAll();
    return { data, message: 'Brands fetched' };
  }

  @ApiBearerAuth()
  @UseGuards(RolesGuard)
  @Roles(UserRole.ADMIN)
  @Post()
  @Version('1')
  @ApiOperation({ summary: '[Admin] Create a brand' })
  async create(@Body() dto: CreateBrandDto) {
    const data = await this.brands.create(dto);
    return { data, message: 'Brand created' };
  }

  @ApiBearerAuth()
  @UseGuards(RolesGuard)
  @Roles(UserRole.ADMIN)
  @Patch(':id')
  @Version('1')
  @ApiOperation({ summary: '[Admin] Update a brand' })
  async update(
    @Param('id', ParseUUIDPipe) id: string,
    @Body() dto: UpdateBrandDto,
  ) {
    const data = await this.brands.update(id, dto);
    return { data, message: 'Brand updated' };
  }

  @ApiBearerAuth()
  @UseGuards(RolesGuard)
  @Roles(UserRole.ADMIN)
  @Delete(':id')
  @Version('1')
  @ApiOperation({ summary: '[Admin] Delete a brand' })
  async remove(@Param('id', ParseUUIDPipe) id: string) {
    await this.brands.remove(id);
    return { data: null, message: 'Brand deleted' };
  }
}
