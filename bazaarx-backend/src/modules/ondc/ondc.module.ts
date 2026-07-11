import { Module } from '@nestjs/common';
import { TypeOrmModule } from '@nestjs/typeorm';
import { Product } from '../catalog/entities/product.entity';
import { ProductVariant } from '../catalog/entities/product-variant.entity';
import { BecknContextService } from './services/beckn-context.service';
import { OndcCatalogService } from './services/ondc-catalog.service';
import { OndcBppService } from './services/ondc-bpp.service';
import { OndcController } from './controllers/ondc.controller';

/**
 * ONDC (Beckn) adapter — BazaarX as a BPP on India's open commerce
 * network. Maps the catalogue to ONDC format and implements the
 * search → confirm → status action flow. Signing is config-gated.
 */
@Module({
  imports: [TypeOrmModule.forFeature([Product, ProductVariant])],
  controllers: [OndcController],
  providers: [BecknContextService, OndcCatalogService, OndcBppService],
  exports: [BecknContextService],
})
export class OndcModule {}
