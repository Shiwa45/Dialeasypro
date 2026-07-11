import {
  Controller,
  Get,
  Param,
  Version,
  ParseUUIDPipe,
  Res,
  StreamableFile,
} from '@nestjs/common';
import { ApiTags, ApiOperation, ApiBearerAuth } from '@nestjs/swagger';
import { Response } from 'express';
import { InvoiceService } from '../services/invoice.service';
import { CurrentUser } from '../../auth/decorators/current-user.decorator';
import { UserRole } from '../../users/entities/user.entity';

@ApiTags('Invoices')
@ApiBearerAuth()
@Controller()
export class InvoiceController {
  constructor(private readonly invoices: InvoiceService) {}

  @Get('orders/:orderId/invoices')
  @Version('1')
  @ApiOperation({ summary: 'List GST invoices for an order' })
  async list(
    @CurrentUser() user: { id: string; role: UserRole },
    @Param('orderId', ParseUUIDPipe) orderId: string,
  ) {
    const data = await this.invoices.listForOrder(orderId, user.id, user.role);
    return { data, message: 'Invoices fetched' };
  }

  @Get('orders/:orderId/sellers/:sellerId/invoice.pdf')
  @Version('1')
  @ApiOperation({ summary: 'Download a seller’s GST invoice PDF for an order' })
  async download(
    @CurrentUser() user: { id: string; role: UserRole },
    @Param('orderId', ParseUUIDPipe) orderId: string,
    @Param('sellerId', ParseUUIDPipe) sellerId: string,
    @Res({ passthrough: true }) res: Response,
  ): Promise<StreamableFile> {
    const { invoice, pdf } = await this.invoices.getPdf(
      orderId,
      sellerId,
      user.id,
      user.role,
    );
    res.set({
      'Content-Type': 'application/pdf',
      'Content-Disposition': `attachment; filename="${invoice.invoiceNumber}.pdf"`,
    });
    return new StreamableFile(pdf);
  }
}
