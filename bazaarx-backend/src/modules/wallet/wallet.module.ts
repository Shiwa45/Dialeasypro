import { Module } from '@nestjs/common';
import { TypeOrmModule } from '@nestjs/typeorm';
import {
  Wallet,
  WalletTransaction,
  BnplAccount,
} from './entities/wallet.entity';
import { WalletService } from './services/wallet.service';
import { WalletController } from './controllers/wallet.controller';
import { PaymentsModule } from '../payments/payments.module';

/**
 * Wallet & BNPL. Exports WalletService so checkout can pay-with-wallet /
 * charge BNPL and returns can refund-to-wallet. Imports PaymentsModule
 * for the Razorpay gateway (top-ups).
 */
@Module({
  imports: [
    TypeOrmModule.forFeature([Wallet, WalletTransaction, BnplAccount]),
    PaymentsModule,
  ],
  controllers: [WalletController],
  providers: [WalletService],
  exports: [WalletService],
})
export class WalletModule {}
