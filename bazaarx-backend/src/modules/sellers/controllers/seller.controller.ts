import {
  Body,
  Controller,
  Get,
  Post,
  Patch,
  Param,
  Query,
  Version,
  ParseUUIDPipe,
  UseGuards,
  HttpCode,
  HttpStatus,
} from '@nestjs/common';
import { ApiTags, ApiOperation, ApiBearerAuth } from '@nestjs/swagger';
import { SellerService } from '../services/seller.service';
import {
  RegisterSellerDto,
  UpdateSellerDto,
  RejectSellerDto,
} from '../dto/seller.dto';
import { SellerStatus } from '../entities/seller.entity';
import { Roles } from '../../auth/decorators/roles.decorator';
import { RolesGuard } from '../../auth/guards/roles.guard';
import { CurrentUser } from '../../auth/decorators/current-user.decorator';
import { UserRole } from '../../users/entities/user.entity';
import { PaginationQueryDto } from '../../../common/dto/pagination-query.dto';

@ApiTags('Sellers')
@ApiBearerAuth()
@Controller('sellers')
export class SellerController {
  constructor(private readonly sellers: SellerService) {}

  // -------- Applicant / Seller (self-serve) --------

  @Post('register')
  @Version('1')
  @ApiOperation({ summary: 'Apply to become a seller (any logged-in user)' })
  async register(
    @CurrentUser('id') userId: string,
    @Body() dto: RegisterSellerDto,
  ) {
    const data = await this.sellers.register(userId, dto);
    return { data, message: 'Seller application submitted for review' };
  }

  @Get('me')
  @Version('1')
  @ApiOperation({ summary: 'Get my seller profile / application status' })
  async getMine(@CurrentUser('id') userId: string) {
    const data = await this.sellers.getMine(userId);
    return { data, message: 'Seller profile fetched' };
  }

  @Patch('me')
  @Version('1')
  @ApiOperation({ summary: 'Update my store / bank details' })
  async updateMine(
    @CurrentUser('id') userId: string,
    @Body() dto: UpdateSellerDto,
  ) {
    const data = await this.sellers.updateMine(userId, dto);
    return { data, message: 'Seller profile updated' };
  }

  // -------- Admin --------

  @UseGuards(RolesGuard)
  @Roles(UserRole.ADMIN)
  @Get('admin/pending')
  @Version('1')
  @ApiOperation({ summary: '[Admin] Sellers awaiting approval' })
  pending(@Query() query: PaginationQueryDto) {
    return this.sellers.findByStatus(SellerStatus.PENDING, query);
  }

  @UseGuards(RolesGuard)
  @Roles(UserRole.ADMIN)
  @Post(':id/approve')
  @Version('1')
  @HttpCode(HttpStatus.OK)
  @ApiOperation({ summary: '[Admin] Approve a seller (promotes user role)' })
  async approve(
    @CurrentUser('id') adminId: string,
    @Param('id', ParseUUIDPipe) id: string,
  ) {
    const data = await this.sellers.approve(id, adminId);
    return { data, message: 'Seller approved' };
  }

  @UseGuards(RolesGuard)
  @Roles(UserRole.ADMIN)
  @Post(':id/reject')
  @Version('1')
  @HttpCode(HttpStatus.OK)
  @ApiOperation({ summary: '[Admin] Reject a seller application' })
  async reject(
    @Param('id', ParseUUIDPipe) id: string,
    @Body() dto: RejectSellerDto,
  ) {
    const data = await this.sellers.reject(id, dto.reason);
    return { data, message: 'Seller application rejected' };
  }

  @UseGuards(RolesGuard)
  @Roles(UserRole.ADMIN)
  @Post(':id/suspend')
  @Version('1')
  @HttpCode(HttpStatus.OK)
  @ApiOperation({ summary: '[Admin] Suspend a seller' })
  async suspend(
    @Param('id', ParseUUIDPipe) id: string,
    @Body() dto: RejectSellerDto,
  ) {
    const data = await this.sellers.suspend(id, dto.reason);
    return { data, message: 'Seller suspended' };
  }
}
