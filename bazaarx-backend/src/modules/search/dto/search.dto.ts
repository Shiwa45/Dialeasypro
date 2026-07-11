import { ApiPropertyOptional } from '@nestjs/swagger';
import { Type } from 'class-transformer';
import { IsString, IsOptional, IsInt, Min, IsIn } from 'class-validator';

export class SearchQueryDto {
  @ApiPropertyOptional({ description: 'Search text' })
  @IsOptional()
  @IsString()
  q?: string;

  @ApiPropertyOptional()
  @IsOptional()
  @IsString()
  categoryId?: string;

  @ApiPropertyOptional()
  @IsOptional()
  @IsString()
  brand?: string;

  @ApiPropertyOptional({ description: 'Min price in paise' })
  @IsOptional()
  @Type(() => Number)
  @IsInt()
  @Min(0)
  minPrice?: number;

  @ApiPropertyOptional({ description: 'Max price in paise' })
  @IsOptional()
  @Type(() => Number)
  @IsInt()
  @Min(0)
  maxPrice?: number;

  @ApiPropertyOptional({ enum: ['relevance', 'price_asc', 'price_desc', 'rating', 'newest'] })
  @IsOptional()
  @IsIn(['relevance', 'price_asc', 'price_desc', 'rating', 'newest'])
  sort?: 'relevance' | 'price_asc' | 'price_desc' | 'rating' | 'newest';

  @ApiPropertyOptional({ default: 1 })
  @IsOptional()
  @Type(() => Number)
  @IsInt()
  @Min(1)
  page: number = 1;

  @ApiPropertyOptional({ default: 20 })
  @IsOptional()
  @Type(() => Number)
  @IsInt()
  @Min(1)
  limit: number = 20;
}

export class SuggestQueryDto {
  @ApiPropertyOptional({ description: 'Partial text for autocomplete' })
  @IsString()
  q: string;
}
