import { Module } from '@nestjs/common';
import { TypeOrmModule } from '@nestjs/typeorm';
import { Coupon } from './entities/coupon.entity';
import { CouponRedemption } from './entities/coupon-redemption.entity';
import { Product } from '../catalog/entities/product.entity';
import { CouponService } from './services/coupon.service';
import { CouponController } from './controllers/coupon.controller';
import { CartModule } from '../cart/cart.module';

/**
 * Promotions & coupons. Exports CouponService so checkout can validate
 * and redeem coupons during order placement.
 */
@Module({
  imports: [
    TypeOrmModule.forFeature([Coupon, CouponRedemption, Product]),
    CartModule,
  ],
  controllers: [CouponController],
  providers: [CouponService],
  exports: [CouponService],
})
export class PromotionsModule {}
