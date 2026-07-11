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
import { ReviewService } from '../services/review.service';
import {
  CreateReviewDto,
  UpdateReviewDto,
  SellerResponseDto,
} from '../dto/review.dto';
import { Public } from '../../auth/decorators/public.decorator';
import { CurrentUser } from '../../auth/decorators/current-user.decorator';
import { Roles } from '../../auth/decorators/roles.decorator';
import { RolesGuard } from '../../auth/guards/roles.guard';
import { UserRole } from '../../users/entities/user.entity';
import { PaginationQueryDto } from '../../../common/dto/pagination-query.dto';

@ApiTags('Reviews & Ratings')
@Controller()
export class ReviewController {
  constructor(private readonly reviews: ReviewService) {}

  @ApiBearerAuth()
  @Post('products/:productId/reviews')
  @Version('1')
  @ApiOperation({ summary: 'Write a review (verified purchase required)' })
  async create(
    @CurrentUser('id') userId: string,
    @Param('productId', ParseUUIDPipe) productId: string,
    @Body() dto: CreateReviewDto,
  ) {
    const data = await this.reviews.create(userId, productId, dto);
    return { data, message: 'Review submitted' };
  }

  @Public()
  @Get('products/:productId/reviews')
  @Version('1')
  @ApiOperation({ summary: 'List reviews for a product' })
  list(
    @Param('productId', ParseUUIDPipe) productId: string,
    @Query() query: PaginationQueryDto,
  ) {
    return this.reviews.list(productId, query);
  }

  @Public()
  @Get('products/:productId/reviews/summary')
  @Version('1')
  @ApiOperation({ summary: 'Star-rating breakdown for a product' })
  async summary(@Param('productId', ParseUUIDPipe) productId: string) {
    const data = await this.reviews.summary(productId);
    return { data, message: 'Rating summary' };
  }

  @ApiBearerAuth()
  @Patch('reviews/:id')
  @Version('1')
  @ApiOperation({ summary: 'Edit my review' })
  async update(
    @CurrentUser('id') userId: string,
    @Param('id', ParseUUIDPipe) id: string,
    @Body() dto: UpdateReviewDto,
  ) {
    const data = await this.reviews.update(userId, id, dto);
    return { data, message: 'Review updated' };
  }

  @ApiBearerAuth()
  @Delete('reviews/:id')
  @Version('1')
  @ApiOperation({ summary: 'Delete my review (or admin)' })
  async remove(
    @CurrentUser() user: { id: string; role: UserRole },
    @Param('id', ParseUUIDPipe) id: string,
  ) {
    await this.reviews.remove(user.id, user.role, id);
    return { data: null, message: 'Review deleted' };
  }

  @ApiBearerAuth()
  @Post('reviews/:id/helpful')
  @Version('1')
  @HttpCode(HttpStatus.OK)
  @ApiOperation({ summary: 'Mark a review as helpful' })
  async helpful(
    @CurrentUser('id') userId: string,
    @Param('id', ParseUUIDPipe) id: string,
  ) {
    const data = await this.reviews.markHelpful(userId, id);
    return { data, message: 'Marked helpful' };
  }

  @ApiBearerAuth()
  @UseGuards(RolesGuard)
  @Roles(UserRole.SELLER, UserRole.ADMIN)
  @Post('reviews/:id/response')
  @Version('1')
  @HttpCode(HttpStatus.OK)
  @ApiOperation({ summary: '[Seller] Respond to a review on your product' })
  async respond(
    @CurrentUser() user: { id: string; role: UserRole },
    @Param('id', ParseUUIDPipe) id: string,
    @Body() dto: SellerResponseDto,
  ) {
    const data = await this.reviews.respond(user.id, user.role, id, dto.response);
    return { data, message: 'Response posted' };
  }
}
