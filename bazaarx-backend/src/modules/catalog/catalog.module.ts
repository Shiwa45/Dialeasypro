import { Module } from '@nestjs/common';
import { TypeOrmModule } from '@nestjs/typeorm';
import { Category } from './entities/category.entity';
import { Brand } from './entities/brand.entity';
import { Product } from './entities/product.entity';
import { ProductVariant } from './entities/product-variant.entity';
import { CategoryService } from './services/category.service';
import { BrandService } from './services/brand.service';
import { ProductService } from './services/product.service';
import { CategoryController } from './controllers/category.controller';
import { BrandController } from './controllers/brand.controller';
import { ProductController } from './controllers/product.controller';

@Module({
  imports: [
    TypeOrmModule.forFeature([Category, Brand, Product, ProductVariant]),
  ],
  controllers: [CategoryController, BrandController, ProductController],
  providers: [CategoryService, BrandService, ProductService],
  exports: [CategoryService, BrandService, ProductService, TypeOrmModule],
})
export class CatalogModule {}
