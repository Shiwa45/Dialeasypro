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
  HttpCode,
  HttpStatus,
} from '@nestjs/common';
import { ApiTags, ApiOperation, ApiBearerAuth } from '@nestjs/swagger';
import { CartService } from './cart.service';
import { AddCartItemDto, UpdateCartItemDto } from './dto/cart.dto';
import { CurrentUser } from '../auth/decorators/current-user.decorator';

@ApiTags('Cart')
@ApiBearerAuth()
@Controller('cart')
export class CartController {
  constructor(private readonly cart: CartService) {}

  @Get()
  @Version('1')
  @ApiOperation({ summary: 'Get my cart (enriched with live prices & stock)' })
  async get(@CurrentUser('id') userId: string) {
    const data = await this.cart.getCart(userId);
    return { data, message: 'Cart fetched' };
  }

  @Post('items')
  @Version('1')
  @ApiOperation({ summary: 'Add an item to the cart' })
  async add(
    @CurrentUser('id') userId: string,
    @Body() dto: AddCartItemDto,
  ) {
    const data = await this.cart.addItem(userId, dto.variantId, dto.quantity);
    return { data, message: 'Item added to cart' };
  }

  @Patch('items/:variantId')
  @Version('1')
  @ApiOperation({ summary: 'Update an item quantity' })
  async update(
    @CurrentUser('id') userId: string,
    @Param('variantId', ParseUUIDPipe) variantId: string,
    @Body() dto: UpdateCartItemDto,
  ) {
    const data = await this.cart.updateItem(userId, variantId, dto.quantity);
    return { data, message: 'Cart updated' };
  }

  @Delete('items/:variantId')
  @Version('1')
  @ApiOperation({ summary: 'Remove an item from the cart' })
  async remove(
    @CurrentUser('id') userId: string,
    @Param('variantId', ParseUUIDPipe) variantId: string,
  ) {
    const data = await this.cart.removeItem(userId, variantId);
    return { data, message: 'Item removed' };
  }

  @Delete()
  @Version('1')
  @ApiOperation({ summary: 'Clear the cart' })
  async clear(@CurrentUser('id') userId: string) {
    const data = await this.cart.clear(userId);
    return { data, message: 'Cart cleared' };
  }

  // -------- Save for later --------

  @Get('saved')
  @Version('1')
  @ApiOperation({ summary: 'Get saved-for-later items' })
  async saved(@CurrentUser('id') userId: string) {
    const data = await this.cart.getSaved(userId);
    return { data, message: 'Saved items fetched' };
  }

  @Post('items/:variantId/save-for-later')
  @Version('1')
  @HttpCode(HttpStatus.OK)
  @ApiOperation({ summary: 'Move a cart item to saved-for-later' })
  async saveForLater(
    @CurrentUser('id') userId: string,
    @Param('variantId', ParseUUIDPipe) variantId: string,
  ) {
    const data = await this.cart.saveForLater(userId, variantId);
    return { data, message: 'Moved to saved for later' };
  }

  @Post('saved/:variantId/move-to-cart')
  @Version('1')
  @HttpCode(HttpStatus.OK)
  @ApiOperation({ summary: 'Move a saved item back to the cart' })
  async moveToCart(
    @CurrentUser('id') userId: string,
    @Param('variantId', ParseUUIDPipe) variantId: string,
  ) {
    const data = await this.cart.moveToCart(userId, variantId);
    return { data, message: 'Moved to cart' };
  }
}
