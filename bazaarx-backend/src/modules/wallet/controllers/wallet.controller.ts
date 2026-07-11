import {
  Body,
  Controller,
  Get,
  Post,
  Query,
  Version,
  HttpCode,
  HttpStatus,
} from '@nestjs/common';
import { ApiTags, ApiOperation, ApiBearerAuth } from '@nestjs/swagger';
import { WalletService } from '../services/wallet.service';
import {
  TopupDto,
  VerifyTopupDto,
  MockPayTopupDto,
  RepayBnplDto,
} from '../dto/wallet.dto';
import { CurrentUser } from '../../auth/decorators/current-user.decorator';
import { PaginationQueryDto } from '../../../common/dto/pagination-query.dto';

@ApiTags('Wallet & BNPL')
@ApiBearerAuth()
@Controller('wallet')
export class WalletController {
  constructor(private readonly wallet: WalletService) {}

  @Get()
  @Version('1')
  @ApiOperation({ summary: 'My wallet balance' })
  async balance(@CurrentUser('id') userId: string) {
    const balance = await this.wallet.balance(userId);
    return { data: { balance }, message: 'Wallet balance' };
  }

  @Get('transactions')
  @Version('1')
  @ApiOperation({ summary: 'My wallet transaction history' })
  history(
    @CurrentUser('id') userId: string,
    @Query() query: PaginationQueryDto,
  ) {
    return this.wallet.history(userId, query);
  }

  @Post('topup')
  @Version('1')
  @HttpCode(HttpStatus.OK)
  @ApiOperation({ summary: 'Start a wallet top-up (returns a gateway order)' })
  async topup(@CurrentUser('id') userId: string, @Body() dto: TopupDto) {
    const data = await this.wallet.initiateTopup(userId, dto.amount);
    return { data, message: 'Top-up initiated' };
  }

  @Post('topup/verify')
  @Version('1')
  @HttpCode(HttpStatus.OK)
  @ApiOperation({ summary: 'Verify a top-up payment and credit the wallet' })
  async verify(
    @CurrentUser('id') userId: string,
    @Body() dto: VerifyTopupDto,
  ) {
    const data = await this.wallet.verifyTopup(
      userId,
      dto.gatewayOrderId,
      dto.gatewayPaymentId,
      dto.signature,
    );
    return { data, message: 'Wallet credited' };
  }

  @Post('topup/mock-pay')
  @Version('1')
  @HttpCode(HttpStatus.OK)
  @ApiOperation({ summary: '[DEV] Simulate a successful top-up (mock mode)' })
  async mockPay(
    @CurrentUser('id') userId: string,
    @Body() dto: MockPayTopupDto,
  ) {
    const data = await this.wallet.mockPayTopup(userId, dto.gatewayOrderId);
    return { data, message: 'Wallet credited (mock)' };
  }

  // -------- BNPL --------

  @Get('bnpl')
  @Version('1')
  @ApiOperation({ summary: 'My BNPL credit line' })
  async bnpl(@CurrentUser('id') userId: string) {
    const acc = await this.wallet.getBnpl(userId);
    return {
      data: {
        creditLimit: acc.creditLimit,
        used: acc.used,
        available: acc.creditLimit - acc.used,
        isActive: acc.isActive,
      },
      message: 'BNPL account',
    };
  }

  @Post('bnpl/repay')
  @Version('1')
  @HttpCode(HttpStatus.OK)
  @ApiOperation({ summary: 'Repay BNPL from wallet balance' })
  async repay(
    @CurrentUser('id') userId: string,
    @Body() dto: RepayBnplDto,
  ) {
    const data = await this.wallet.repayBnpl(userId, dto.amount);
    return { data, message: 'BNPL repaid' };
  }
}
