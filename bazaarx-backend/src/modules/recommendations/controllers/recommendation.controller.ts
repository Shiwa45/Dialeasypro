import {
  Controller,
  Get,
  Post,
  Param,
  Query,
  Version,
  ParseUUIDPipe,
  HttpCode,
  HttpStatus,
} from '@nestjs/common';
import { ApiTags, ApiOperation, ApiBearerAuth } from '@nestjs/swagger';
import { RecommendationService } from '../services/recommendation.service';
import { Public } from '../../auth/decorators/public.decorator';
import { CurrentUser } from '../../auth/decorators/current-user.decorator';

function clampLimit(raw: string | undefined, def = 10): number {
  const n = parseInt(raw ?? '', 10);
  return Math.min(Math.max(Number.isNaN(n) ? def : n, 1), 30);
}

@ApiTags('Recommendations')
@Controller()
export class RecommendationController {
  constructor(private readonly recs: RecommendationService) {}

  @Public()
  @Get('products/:productId/related')
  @Version('1')
  @ApiOperation({ summary: 'Related products (same category)' })
  async related(
    @Param('productId', ParseUUIDPipe) productId: string,
    @Query('limit') limit?: string,
  ) {
    const data = await this.recs.related(productId, clampLimit(limit));
    return { data, message: 'Related products' };
  }

  @Public()
  @Get('products/:productId/frequently-bought-together')
  @Version('1')
  @ApiOperation({ summary: 'Products often bought with this one' })
  async fbt(
    @Param('productId', ParseUUIDPipe) productId: string,
    @Query('limit') limit?: string,
  ) {
    const data = await this.recs.frequentlyBoughtTogether(
      productId,
      clampLimit(limit, 5),
    );
    return { data, message: 'Frequently bought together' };
  }

  @Public()
  @Get('recommendations/trending')
  @Version('1')
  @ApiOperation({ summary: 'Trending products (last 30 days)' })
  async trending(@Query('limit') limit?: string) {
    const data = await this.recs.trending(clampLimit(limit));
    return { data, message: 'Trending now' };
  }

  @ApiBearerAuth()
  @Get('recommendations/for-you')
  @Version('1')
  @ApiOperation({ summary: 'Personalized recommendations' })
  async forYou(
    @CurrentUser('id') userId: string,
    @Query('limit') limit?: string,
  ) {
    const data = await this.recs.forYou(userId, clampLimit(limit));
    return { data, message: 'For you' };
  }

  @ApiBearerAuth()
  @Post('products/:productId/view')
  @Version('1')
  @HttpCode(HttpStatus.OK)
  @ApiOperation({ summary: 'Record a product view (for recently-viewed)' })
  async view(
    @CurrentUser('id') userId: string,
    @Param('productId', ParseUUIDPipe) productId: string,
  ) {
    await this.recs.trackView(userId, productId);
    return { data: null, message: 'View recorded' };
  }

  @ApiBearerAuth()
  @Get('recommendations/recently-viewed')
  @Version('1')
  @ApiOperation({ summary: 'My recently viewed products' })
  async recentlyViewed(
    @CurrentUser('id') userId: string,
    @Query('limit') limit?: string,
  ) {
    const data = await this.recs.recentlyViewed(userId, clampLimit(limit));
    return { data, message: 'Recently viewed' };
  }
}
