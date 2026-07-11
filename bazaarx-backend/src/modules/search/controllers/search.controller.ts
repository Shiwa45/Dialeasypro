import {
  Controller,
  Get,
  Post,
  Query,
  Version,
  UseGuards,
  HttpCode,
  HttpStatus,
} from '@nestjs/common';
import { ApiTags, ApiOperation, ApiBearerAuth } from '@nestjs/swagger';
import { SearchService } from '../services/search.service';
import { ProductIndexService } from '../services/product-index.service';
import { SearchQueryDto, SuggestQueryDto } from '../dto/search.dto';
import { Public } from '../../auth/decorators/public.decorator';
import { Roles } from '../../auth/decorators/roles.decorator';
import { RolesGuard } from '../../auth/guards/roles.guard';
import { UserRole } from '../../users/entities/user.entity';

@ApiTags('Search & Discovery')
@Controller('search')
export class SearchController {
  constructor(
    private readonly search: SearchService,
    private readonly index: ProductIndexService,
  ) {}

  @Public()
  @Get()
  @Version('1')
  @ApiOperation({ summary: 'Full-text product search with filters & facets' })
  query(@Query() dto: SearchQueryDto) {
    return this.search.search(dto);
  }

  @Public()
  @Get('suggest')
  @Version('1')
  @ApiOperation({ summary: 'Autocomplete suggestions (search-as-you-type)' })
  async suggest(@Query() dto: SuggestQueryDto) {
    const data = await this.search.suggest(dto.q);
    return { data, message: 'Suggestions' };
  }

  @ApiBearerAuth()
  @UseGuards(RolesGuard)
  @Roles(UserRole.ADMIN)
  @Post('reindex')
  @Version('1')
  @HttpCode(HttpStatus.OK)
  @ApiOperation({ summary: '[Admin] Rebuild the product search index' })
  async reindex() {
    const data = await this.index.reindexAll();
    return { data, message: 'Reindex complete' };
  }
}
