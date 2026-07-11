import {
  Body,
  Controller,
  Post,
  Req,
  Headers,
  Version,
  HttpCode,
  HttpStatus,
  BadRequestException,
} from '@nestjs/common';
import { ApiTags, ApiOperation, ApiBearerAuth } from '@nestjs/swagger';
import { Request } from 'express';
import { PaymentService } from '../services/payment.service';
import { RazorpayService } from '../services/razorpay.service';
import { VerifyPaymentDto } from '../dto/payment.dto';
import { Public } from '../../auth/decorators/public.decorator';
import { CurrentUser } from '../../auth/decorators/current-user.decorator';
import { randomBytes } from 'crypto';

@ApiTags('Payments')
@Controller('payments')
export class PaymentController {
  constructor(
    private readonly payments: PaymentService,
    private readonly razorpay: RazorpayService,
  ) {}

  @ApiBearerAuth()
  @Post('verify')
  @Version('1')
  @HttpCode(HttpStatus.OK)
  @ApiOperation({ summary: 'Verify a completed payment (client callback)' })
  async verify(
    @CurrentUser('id') userId: string,
    @Body() dto: VerifyPaymentDto,
  ) {
    const data = await this.payments.verify(
      userId,
      dto.gatewayOrderId,
      dto.gatewayPaymentId,
      dto.signature,
    );
    return { data, message: 'Payment verified' };
  }

  @Public()
  @Post('webhook')
  @Version('1')
  @HttpCode(HttpStatus.OK)
  @ApiOperation({ summary: 'Razorpay webhook (server-to-server)' })
  async webhook(
    @Req() req: Request & { rawBody?: Buffer },
    @Headers('x-razorpay-signature') signature: string,
  ) {
    const rawBody = req.rawBody?.toString('utf8') ?? JSON.stringify(req.body);
    await this.payments.handleWebhook(rawBody, signature || '');
    return { data: null, message: 'Webhook processed' };
  }

  /**
   * DEV ONLY: simulates a successful Razorpay payment so the verify flow
   * can be exercised locally without a real gateway. Disabled unless the
   * service is running in mock mode (no Razorpay keys configured).
   */
  @ApiBearerAuth()
  @Post('mock/pay')
  @Version('1')
  @HttpCode(HttpStatus.OK)
  @ApiOperation({ summary: '[DEV] Simulate a successful payment (mock mode only)' })
  async mockPay(
    @CurrentUser('id') userId: string,
    @Body() body: { gatewayOrderId: string },
  ) {
    if (!this.razorpay.isMock) {
      throw new BadRequestException('Mock payments are disabled');
    }
    const gatewayPaymentId = `pay_MOCK${randomBytes(8).toString('hex')}`;
    const signature = this.razorpay.mockSignPayment(
      body.gatewayOrderId,
      gatewayPaymentId,
    );
    const data = await this.payments.verify(
      userId,
      body.gatewayOrderId,
      gatewayPaymentId,
      signature,
    );
    return { data, message: 'Mock payment captured' };
  }
}
