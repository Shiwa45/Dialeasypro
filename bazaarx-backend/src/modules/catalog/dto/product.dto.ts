import { ApiProperty, ApiPropertyOptional, PartialType } from '@nestjs/swagger';
import { Type } from 'class-transformer';
import {
  IsString,
  IsOptional,
  IsUUID,
  IsArray,
  IsInt,
  IsObject,
  IsBoolean,
  Length,
  Min,
  ValidateNested,
  ArrayMaxSize,
  IsEnum,
} from 'class-validator';
import { PaginationQueryDto } from '../../../common/dto/pagination-query.dto';
import { ProductStatus } from '../entities/product.entity';

// ---------- Brand ----------
export class CreateBrandDto {
  @ApiProperty({ example: 'Samsung' })
  @IsString()
  @Length(1, 150)
  name: string;

  @ApiPropertyOptional()
  @IsOptional()
  @IsString()
  logoUrl?: string;

  @ApiPropertyOptional()
  @IsOptional()
  @IsString()
  description?: string;
}
export class UpdateBrandDto extends PartialType(CreateBrandDto) {
  @IsOptional() @IsBoolean() isActive?: boolean;
}

// ---------- Variant ----------
export class CreateVariantDto {
  @ApiProperty({ example: 'SAMS-S24-BLK-256' })
  @IsString()
  @Length(1, 100)
  sku: string;

  @ApiProperty({ example: { Color: 'Black', Storage: '256GB' } })
  @IsObject()
  attributes: Record<string, string>;

  @ApiProperty({ example: 9999900, description: 'MRP in paise' })
  @IsInt()
  @Min(0)
  mrp: number;

  @ApiProperty({ example: 8499900, description: 'Selling price in paise' })
  @IsInt()
  @Min(0)
  sellingPrice: number;

  @ApiProperty({ example: 50 })
  @IsInt()
  @Min(0)
  stockQuantity: number;

  @ApiPropertyOptional({ default: 5 })
  @IsOptional()
  @IsInt()
  @Min(0)
  lowStockThreshold?: number;

  @ApiPropertyOptional({ type: [String] })
  @IsOptional()
  @IsArray()
  @IsString({ each: true })
  imageUrls?: string[];

  @ApiPropertyOptional()
  @IsOptional()
  @IsInt()
  @Min(0)
  weightGrams?: number;
}

// ---------- Product ----------
export class CreateProductDto {
  @ApiProperty({ example: 'Samsung Galaxy S24 5G' })
  @IsString()
  @Length(3, 300)
  title: string;

  @ApiProperty()
  @IsUUID()
  categoryId: string;

  @ApiPropertyOptional()
  @IsOptional()
  @IsUUID()
  brandId?: string;

  @ApiPropertyOptional({ example: '85171290', description: 'HSN/SAC code for GST' })
  @IsOptional()
  @IsString()
  hsnCode?: string;

  @ApiPropertyOptional()
  @IsOptional()
  @IsString()
  description?: string;

  @ApiPropertyOptional({ type: [String], description: 'Up to 5 highlights' })
  @IsOptional()
  @IsArray()
  @IsString({ each: true })
  @ArrayMaxSize(5)
  highlights?: string[];

  @ApiPropertyOptional({ example: { RAM: '8GB', Display: '6.2 inch' } })
  @IsOptional()
  @IsObject()
  specifications?: Record<string, string>;

  @ApiPropertyOptional({ type: [String] })
  @IsOptional()
  @IsArray()
  @IsString({ each: true })
  tags?: string[];

  @ApiProperty({ type: [CreateVariantDto] })
  @IsArray()
  @ValidateNested({ each: true })
  @Type(() => CreateVariantDto)
  variants: CreateVariantDto[];
}

export class UpdateProductDto extends PartialType(CreateProductDto) {}

// ---------- Browse query ----------
export class ProductQueryDto extends PaginationQueryDto {
  @ApiPropertyOptional()
  @IsOptional()
  @IsUUID()
  categoryId?: string;

  @ApiPropertyOptional()
  @IsOptional()
  @IsUUID()
  brandId?: string;

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

  @ApiPropertyOptional()
  @IsOptional()
  @IsString()
  search?: string;
}

// ---------- Admin moderation ----------
export class ModerateProductDto {
  @ApiProperty({ enum: [ProductStatus.ACTIVE, ProductStatus.REJECTED] })
  @IsEnum(ProductStatus)
  status: ProductStatus;

  @ApiPropertyOptional()
  @IsOptional()
  @IsString()
  rejectionReason?: string;
}
