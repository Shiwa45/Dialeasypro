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
import { CheckoutService } from '../services/checkout.service';
import { OrderService } from '../services/order.service';
import {
  CheckoutDto,
  CancelOrderItemDto,
  UpdateItemStatusDto,
} from '../dto/order.dto';
import { CurrentUser } from '../../auth/decorators/current-user.decorator';
import { Roles } from '../../auth/decorators/roles.decorator';
import { RolesGuard } from '../../auth/guards/roles.guard';
import { UserRole } from '../../users/entities/user.entity';
import { PaginationQueryDto } from '../../../common/dto/pagination-query.dto';

@ApiTags('Orders & Checkout')
@ApiBearerAuth()
@Controller()
export class OrderController {
  constructor(
    private readonly checkout: CheckoutService,
    private readonly orders: OrderService,
  ) {}

  // -------- Checkout --------

  @Post('checkout')
  @Version('1')
  @HttpCode(HttpStatus.CREATED)
  @ApiOperation({ summary: 'Place an order from the cart' })
  async placeOrder(
    @CurrentUser('id') userId: string,
    @Body() dto: CheckoutDto,
  ) {
    const { order, payment } = await this.checkout.placeOrder(userId, dto);
    return {
      data: { order, payment },
      message: payment
        ? 'Order created — complete payment to confirm'
        : 'Order placed successfully',
    };
  }

  // -------- Buyer orders --------

  @Get('orders')
  @Version('1')
  @ApiOperation({ summary: 'List my orders' })
  list(@CurrentUser('id') userId: string, @Query() query: PaginationQueryDto) {
    return this.orders.findUserOrders(userId, query);
  }

  @Get('orders/:id')
  @Version('1')
  @ApiOperation({ summary: 'Get one of my orders' })
  async detail(
    @CurrentUser('id') userId: string,
    @Param('id', ParseUUIDPipe) id: string,
  ) {
    const data = await this.orders.findUserOrder(userId, id);
    return { data, message: 'Order fetched' };
  }

  @Post('orders/items/:itemId/cancel')
  @Version('1')
  @HttpCode(HttpStatus.OK)
  @ApiOperation({ summary: 'Cancel an order item (pre-dispatch)' })
  async cancel(
    @CurrentUser('id') userId: string,
    @Param('itemId', ParseUUIDPipe) itemId: string,
    @Body() dto: CancelOrderItemDto,
  ) {
    const data = await this.orders.cancelItem(userId, itemId, dto.reason);
    return { data, message: 'Item cancelled' };
  }

  // -------- Seller fulfillment --------

  @UseGuards(RolesGuard)
  @Roles(UserRole.SELLER)
  @Get('seller/order-items')
  @Version('1')
  @ApiOperation({ summary: '[Seller] Items to fulfill' })
  sellerItems(
    @CurrentUser('id') sellerId: string,
    @Query() query: PaginationQueryDto,
  ) {
    return this.orders.findSellerItems(sellerId, query);
  }

  @UseGuards(RolesGuard)
  @Roles(UserRole.SELLER)
  @Patch('seller/order-items/:itemId/status')
  @Version('1')
  @ApiOperation({ summary: '[Seller] Advance an item’s fulfillment status' })
  async updateStatus(
    @CurrentUser('id') sellerId: string,
    @Param('itemId', ParseUUIDPipe) itemId: string,
    @Body() dto: UpdateItemStatusDto,
  ) {
    const data = await this.orders.updateItemStatus(
      sellerId,
      itemId,
      dto.status,
      dto.awbNumber,
    );
    return { data, message: `Item marked ${dto.status}` };
  }
}
