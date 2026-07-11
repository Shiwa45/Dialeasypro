import { Module } from '@nestjs/common';
import { TypeOrmModule } from '@nestjs/typeorm';
import { Invoice } from './entities/invoice.entity';
import { Order } from '../orders/entities/order.entity';
import { OrderItem } from '../orders/entities/order-item.entity';
import { Seller } from '../sellers/entities/seller.entity';
import { InvoiceService } from './services/invoice.service';
import { InvoicePdfService } from './services/invoice-pdf.service';
import { InvoiceController } from './controllers/invoice.controller';

@Module({
  imports: [TypeOrmModule.forFeature([Invoice, Order, OrderItem, Seller])],
  controllers: [InvoiceController],
  providers: [InvoiceService, InvoicePdfService],
  exports: [InvoiceService],
})
export class InvoicesModule {}
