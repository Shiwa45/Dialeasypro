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
  Headers,
} from '@nestjs/common';
import { ApiTags, ApiOperation, ApiBearerAuth } from '@nestjs/swagger';
import { ShippingService } from '../services/shipping.service';
import { ServiceabilityDto } from '../dto/shipping.dto';
import { Public } from '../../auth/decorators/public.decorator';
import { CurrentUser } from '../../auth/decorators/current-user.decorator';
import { Roles } from '../../auth/decorators/roles.decorator';
import { RolesGuard } from '../../auth/guards/roles.guard';
import { UserRole } from '../../users/entities/user.entity';

@ApiTags('Logistics & Shipping')
@Controller()
export class ShippingController {
  constructor(private readonly shipping: ShippingService) {}

  @Public()
  @Get('shipping/serviceability')
  @Version('1')
  @ApiOperation({ summary: 'Check courier serviceability & delivery estimates' })
  async serviceability(@Query() dto: ServiceabilityDto) {
    const data = await this.shipping.serviceability(
      dto.deliveryPincode,
      dto.weightGrams ?? 500,
      dto.cod ?? true,
    );
    return {
      data,
      message: data.couriers.length
        ? 'Serviceable'
        : 'Not serviceable to this pincode',
    };
  }

  @ApiBearerAuth()
  @UseGuards(RolesGuard)
  @Roles(UserRole.SELLER)
  @Post('seller/orders/:orderId/shipment')
  @Version('1')
  @HttpCode(HttpStatus.CREATED)
  @ApiOperation({ summary: '[Seller] Create a courier shipment & assign AWB' })
  async ship(
    @CurrentUser('id') sellerId: string,
    @Param('orderId', ParseUUIDPipe) orderId: string,
  ) {
    const data = await this.shipping.createShipment(sellerId, orderId);
    return { data, message: 'Shipment created and AWB assigned' };
  }

  @ApiBearerAuth()
  @Get('shipments/:id/track')
  @Version('1')
  @ApiOperation({ summary: 'Track a shipment' })
  async track(
    @CurrentUser() user: { id: string; role: UserRole },
    @Param('id', ParseUUIDPipe) id: string,
  ) {
    const data = await this.shipping.track(id, user.id, user.role);
    return { data, message: 'Tracking updated' };
  }

  @Public()
  @Post('shipping/webhook')
  @Version('1')
  @HttpCode(HttpStatus.OK)
  @ApiOperation({ summary: 'Shiprocket tracking webhook' })
  async webhook(
    @Headers('x-api-key') token: string,
    @Body() payload: any,
  ) {
    await this.shipping.handleWebhook(token, payload);
    return { data: null, message: 'Webhook processed' };
  }
}
