import {
  Body,
  Controller,
  Get,
  Post,
  Patch,
  Param,
  Version,
  ParseUUIDPipe,
  UseGuards,
  HttpCode,
  HttpStatus,
} from '@nestjs/common';
import { ApiTags, ApiOperation, ApiBearerAuth } from '@nestjs/swagger';
import { CouponService } from '../services/coupon.service';
import { CartService } from '../../cart/cart.service';
import { CreateCouponDto, ValidateCouponDto } from '../dto/coupon.dto';
import { Public } from '../../auth/decorators/public.decorator';
import { CurrentUser } from '../../auth/decorators/current-user.decorator';
import { Roles } from '../../auth/decorators/roles.decorator';
import { RolesGuard } from '../../auth/guards/roles.guard';
import { UserRole } from '../../users/entities/user.entity';

@ApiTags('Promotions & Coupons')
@Controller('coupons')
export class CouponController {
  constructor(
    private readonly coupons: CouponService,
    private readonly cart: CartService,
  ) {}

  @ApiBearerAuth()
  @UseGuards(RolesGuard)
  @Roles(UserRole.ADMIN, UserRole.SELLER)
  @Post()
  @Version('1')
  @ApiOperation({ summary: '[Admin/Seller] Create a coupon' })
  async create(
    @CurrentUser() user: { id: string; role: UserRole },
    @Body() dto: CreateCouponDto,
  ) {
    const data = await this.coupons.create(user.id, user.role, dto);
    return { data, message: 'Coupon created' };
  }

  @Public()
  @Get('active')
  @Version('1')
  @ApiOperation({ summary: 'List active platform-wide coupons' })
  async active() {
    const data = await this.coupons.listActivePublic();
    return { data, message: 'Active coupons' };
  }

  @ApiBearerAuth()
  @UseGuards(RolesGuard)
  @Roles(UserRole.ADMIN)
  @Get()
  @Version('1')
  @ApiOperation({ summary: '[Admin] List all coupons' })
  async all() {
    const data = await this.coupons.listAll();
    return { data, message: 'All coupons' };
  }

  @ApiBearerAuth()
  @UseGuards(RolesGuard)
  @Roles(UserRole.ADMIN, UserRole.SELLER)
  @Patch(':id/deactivate')
  @Version('1')
  @ApiOperation({ summary: '[Admin/Seller] Deactivate a coupon' })
  async deactivate(
    @CurrentUser() user: { id: string; role: UserRole },
    @Param('id', ParseUUIDPipe) id: string,
  ) {
    const data = await this.coupons.deactivate(user.id, user.role, id);
    return { data, message: 'Coupon deactivated' };
  }

  @ApiBearerAuth()
  @Post('validate')
  @Version('1')
  @HttpCode(HttpStatus.OK)
  @ApiOperation({ summary: 'Preview a coupon discount against my cart' })
  async validate(
    @CurrentUser('id') userId: string,
    @Body() dto: ValidateCouponDto,
  ) {
    const cart = await this.cart.getCart(userId);
    const lines = cart.items.map((i) => ({
      productId: i.productId,
      lineTotal: i.lineTotal,
    }));
    const { coupon, discount, eligibleSubtotal } =
      await this.coupons.validateAndCompute(dto.code, userId, lines);
    return {
      data: {
        code: coupon.code,
        discountType: coupon.discountType,
        discount,
        eligibleSubtotal,
        newTotal: cart.summary.subtotal - discount,
      },
      message: 'Coupon applied',
    };
  }
}
