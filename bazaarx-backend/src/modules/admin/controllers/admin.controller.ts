import {
  Body,
  Controller,
  Get,
  Patch,
  Param,
  Query,
  Version,
  ParseUUIDPipe,
  UseGuards,
} from '@nestjs/common';
import { ApiTags, ApiOperation, ApiBearerAuth } from '@nestjs/swagger';
import { AdminService } from '../services/admin.service';
import { SetRoleDto, AdminUserQueryDto } from '../dto/admin.dto';
import { Roles } from '../../auth/decorators/roles.decorator';
import { RolesGuard } from '../../auth/guards/roles.guard';
import { UserRole } from '../../users/entities/user.entity';
import { PaginationQueryDto } from '../../../common/dto/pagination-query.dto';

@ApiTags('Admin Panel')
@ApiBearerAuth()
@UseGuards(RolesGuard)
@Roles(UserRole.ADMIN)
@Controller('admin')
export class AdminController {
  constructor(private readonly admin: AdminService) {}

  @Get('overview')
  @Version('1')
  @ApiOperation({ summary: 'Platform KPIs & moderation backlog' })
  async overview() {
    const data = await this.admin.overview();
    return { data, message: 'Platform overview' };
  }

  // -------- Users --------

  @Get('users')
  @Version('1')
  @ApiOperation({ summary: 'List/search users' })
  users(@Query() query: AdminUserQueryDto) {
    return this.admin.listUsers(query, query.search, query.role);
  }

  @Patch('users/:id/suspend')
  @Version('1')
  @ApiOperation({ summary: 'Suspend a user (blocks login)' })
  async suspend(@Param('id', ParseUUIDPipe) id: string) {
    const data = await this.admin.setUserActive(id, false);
    return { data, message: 'User suspended' };
  }

  @Patch('users/:id/activate')
  @Version('1')
  @ApiOperation({ summary: 'Reactivate a suspended user' })
  async activate(@Param('id', ParseUUIDPipe) id: string) {
    const data = await this.admin.setUserActive(id, true);
    return { data, message: 'User reactivated' };
  }

  @Patch('users/:id/role')
  @Version('1')
  @ApiOperation({ summary: 'Change a user role' })
  async role(
    @Param('id', ParseUUIDPipe) id: string,
    @Body() dto: SetRoleDto,
  ) {
    const data = await this.admin.setUserRole(id, dto.role);
    return { data, message: 'Role updated' };
  }

  // -------- Moderation queues --------

  @Get('products/pending')
  @Version('1')
  @ApiOperation({ summary: 'Products awaiting moderation' })
  pendingProducts(@Query() query: PaginationQueryDto) {
    return this.admin.pendingProducts(query);
  }

  @Get('sellers/pending')
  @Version('1')
  @ApiOperation({ summary: 'Sellers awaiting approval' })
  pendingSellers(@Query() query: PaginationQueryDto) {
    return this.admin.pendingSellers(query);
  }

  @Get('orders')
  @Version('1')
  @ApiOperation({ summary: 'All orders (oversight)' })
  orders(@Query() query: PaginationQueryDto) {
    return this.admin.allOrders(query);
  }

  // -------- Review moderation --------

  @Patch('reviews/:id/hide')
  @Version('1')
  @ApiOperation({ summary: 'Hide a review' })
  async hideReview(@Param('id', ParseUUIDPipe) id: string) {
    const data = await this.admin.moderateReview(id, true);
    return { data, message: 'Review hidden' };
  }

  @Patch('reviews/:id/show')
  @Version('1')
  @ApiOperation({ summary: 'Unhide a review' })
  async showReview(@Param('id', ParseUUIDPipe) id: string) {
    const data = await this.admin.moderateReview(id, false);
    return { data, message: 'Review visible' };
  }
}
