import {
  Body,
  Controller,
  Get,
  Post,
  Param,
  Query,
  Version,
  ParseUUIDPipe,
  UseGuards,
  HttpCode,
  HttpStatus,
} from '@nestjs/common';
import { ApiTags, ApiOperation, ApiBearerAuth } from '@nestjs/swagger';
import { ReturnService } from '../services/return.service';
import { RequestReturnDto, RejectReturnDto } from '../dto/return.dto';
import { CurrentUser } from '../../auth/decorators/current-user.decorator';
import { Roles } from '../../auth/decorators/roles.decorator';
import { RolesGuard } from '../../auth/guards/roles.guard';
import { UserRole } from '../../users/entities/user.entity';
import { PaginationQueryDto } from '../../../common/dto/pagination-query.dto';

@ApiTags('Returns & Refunds')
@ApiBearerAuth()
@Controller()
export class ReturnController {
  constructor(private readonly returns: ReturnService) {}

  // -------- Buyer --------

  @Post('returns')
  @Version('1')
  @HttpCode(HttpStatus.CREATED)
  @ApiOperation({ summary: 'Request a return on a delivered item' })
  async request(
    @CurrentUser('id') buyerId: string,
    @Body() dto: RequestReturnDto,
  ) {
    const data = await this.returns.requestReturn(buyerId, dto);
    return { data, message: 'Return requested' };
  }

  @Get('returns')
  @Version('1')
  @ApiOperation({ summary: 'List my returns' })
  listMine(
    @CurrentUser('id') buyerId: string,
    @Query() query: PaginationQueryDto,
  ) {
    return this.returns.listForBuyer(buyerId, query);
  }

  @Post('returns/:id/cancel')
  @Version('1')
  @HttpCode(HttpStatus.OK)
  @ApiOperation({ summary: 'Cancel my return request' })
  async cancel(
    @CurrentUser('id') buyerId: string,
    @Param('id', ParseUUIDPipe) id: string,
  ) {
    const data = await this.returns.cancel(buyerId, id);
    return { data, message: 'Return cancelled' };
  }

  // -------- Seller / Admin --------

  @UseGuards(RolesGuard)
  @Roles(UserRole.SELLER)
  @Get('seller/returns')
  @Version('1')
  @ApiOperation({ summary: '[Seller] List returns on my items' })
  listSeller(
    @CurrentUser('id') sellerId: string,
    @Query() query: PaginationQueryDto,
  ) {
    return this.returns.listForSeller(sellerId, query);
  }

  @UseGuards(RolesGuard)
  @Roles(UserRole.SELLER, UserRole.ADMIN)
  @Post('returns/:id/approve')
  @Version('1')
  @HttpCode(HttpStatus.OK)
  @ApiOperation({ summary: '[Seller/Admin] Approve a return & create reverse pickup' })
  async approve(
    @CurrentUser() user: { id: string; role: UserRole },
    @Param('id', ParseUUIDPipe) id: string,
  ) {
    const data = await this.returns.approve(user.id, user.role, id);
    return { data, message: 'Return approved; reverse pickup created' };
  }

  @UseGuards(RolesGuard)
  @Roles(UserRole.SELLER, UserRole.ADMIN)
  @Post('returns/:id/reject')
  @Version('1')
  @HttpCode(HttpStatus.OK)
  @ApiOperation({ summary: '[Seller/Admin] Reject a return' })
  async reject(
    @CurrentUser() user: { id: string; role: UserRole },
    @Param('id', ParseUUIDPipe) id: string,
    @Body() dto: RejectReturnDto,
  ) {
    const data = await this.returns.reject(user.id, user.role, id, dto.reason);
    return { data, message: 'Return rejected' };
  }

  @UseGuards(RolesGuard)
  @Roles(UserRole.SELLER, UserRole.ADMIN)
  @Post('returns/:id/complete')
  @Version('1')
  @HttpCode(HttpStatus.OK)
  @ApiOperation({ summary: '[Seller/Admin] Mark received, refund & restock' })
  async complete(
    @CurrentUser() user: { id: string; role: UserRole },
    @Param('id', ParseUUIDPipe) id: string,
  ) {
    const data = await this.returns.complete(user.id, user.role, id);
    return { data, message: 'Return completed and refund issued' };
  }
}
