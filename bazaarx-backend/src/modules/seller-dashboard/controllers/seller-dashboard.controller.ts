import {
  Controller,
  Get,
  Query,
  Version,
  UseGuards,
} from '@nestjs/common';
import { ApiTags, ApiOperation, ApiBearerAuth } from '@nestjs/swagger';
import { SellerDashboardService } from '../services/seller-dashboard.service';
import { CurrentUser } from '../../auth/decorators/current-user.decorator';
import { Roles } from '../../auth/decorators/roles.decorator';
import { RolesGuard } from '../../auth/guards/roles.guard';
import { UserRole } from '../../users/entities/user.entity';

@ApiTags('Seller Dashboard')
@ApiBearerAuth()
@UseGuards(RolesGuard)
@Roles(UserRole.SELLER)
@Controller('seller/dashboard')
export class SellerDashboardController {
  constructor(private readonly dashboard: SellerDashboardService) {}

  @Get('overview')
  @Version('1')
  @ApiOperation({ summary: 'Headline KPIs (revenue, orders, rating, returns)' })
  async overview(@CurrentUser('id') sellerId: string) {
    const data = await this.dashboard.overview(sellerId);
    return { data, message: 'Overview' };
  }

  @Get('sales')
  @Version('1')
  @ApiOperation({ summary: 'Sales trend (period: 7d | 30d | 12m)' })
  async sales(
    @CurrentUser('id') sellerId: string,
    @Query('period') period: '7d' | '30d' | '12m' = '30d',
  ) {
    const p = ['7d', '30d', '12m'].includes(period) ? period : '30d';
    const data = await this.dashboard.salesTrend(sellerId, p);
    return { data, message: 'Sales trend' };
  }

  @Get('orders-by-status')
  @Version('1')
  @ApiOperation({ summary: 'Item counts & value by fulfillment status' })
  async byStatus(@CurrentUser('id') sellerId: string) {
    const data = await this.dashboard.ordersByStatus(sellerId);
    return { data, message: 'Orders by status' };
  }

  @Get('top-products')
  @Version('1')
  @ApiOperation({ summary: 'Best-selling products by revenue' })
  async top(
    @CurrentUser('id') sellerId: string,
    @Query('limit') limit = '10',
  ) {
    const n = Math.min(Math.max(parseInt(limit, 10) || 10, 1), 50);
    const data = await this.dashboard.topProducts(sellerId, n);
    return { data, message: 'Top products' };
  }

  @Get('returns')
  @Version('1')
  @ApiOperation({ summary: 'Return analytics (rate, by status & reason)' })
  async returns(@CurrentUser('id') sellerId: string) {
    const data = await this.dashboard.returns(sellerId);
    return { data, message: 'Returns analytics' };
  }

  @Get('settlement')
  @Version('1')
  @ApiOperation({ summary: 'Payout summary (gross, commission, refunds, net)' })
  async settlement(@CurrentUser('id') sellerId: string) {
    const data = await this.dashboard.settlement(sellerId);
    return { data, message: 'Settlement summary' };
  }
}
