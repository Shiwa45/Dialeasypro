import { Module } from '@nestjs/common';
import { TypeOrmModule } from '@nestjs/typeorm';
import { Seller } from './entities/seller.entity';
import { SellerDocument } from './entities/seller-document.entity';
import { SellerService } from './services/seller.service';
import { SellerController } from './controllers/seller.controller';
import { UsersModule } from '../users/users.module';

@Module({
  imports: [
    TypeOrmModule.forFeature([Seller, SellerDocument]),
    UsersModule,
  ],
  controllers: [SellerController],
  providers: [SellerService],
  exports: [SellerService, TypeOrmModule],
})
export class SellersModule {}
