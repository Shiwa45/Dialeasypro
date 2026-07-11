import { Injectable } from '@nestjs/common';
import PDFDocument = require('pdfkit');

/** Money helper: paise (int) → "₹1,234.56". */
function rupees(paise: number): string {
  return '₹' + (paise / 100).toLocaleString('en-IN', { minimumFractionDigits: 2 });
}

export interface InvoiceLine {
  title: string;
  hsnCode: string;
  quantity: number;
  taxableValue: number;
  gstRate: number;
  cgst: number;
  sgst: number;
  igst: number;
  lineTotal: number;
}

export interface InvoiceData {
  invoiceNumber: string;
  issuedAt: string;
  orderNumber: string;
  isIntraState: boolean;
  seller: { businessName: string; gstin: string; stateName: string };
  buyer: {
    name: string;
    address: string;
    state: string;
    pincode: string;
  };
  lines: InvoiceLine[];
  taxableValue: number;
  totalCgst: number;
  totalSgst: number;
  totalIgst: number;
  totalTax: number;
  grandTotal: number;
}

/**
 * Renders a GST tax invoice to a PDF Buffer with pdfkit.
 * Layout: header, seller/buyer blocks, itemized GST table, totals.
 */
@Injectable()
export class InvoicePdfService {
  async render(data: InvoiceData): Promise<Buffer> {
    const doc = new PDFDocument({ size: 'A4', margin: 40 });
    const chunks: Buffer[] = [];
    doc.on('data', (c) => chunks.push(c as Buffer));

    const done = new Promise<Buffer>((resolve) => {
      doc.on('end', () => resolve(Buffer.concat(chunks)));
    });

    this.build(doc, data);
    doc.end();
    return done;
  }

  private build(doc: PDFKit.PDFDocument, d: InvoiceData) {
    // --- Header ---
    doc.fontSize(20).text('TAX INVOICE', { align: 'center' });
    doc.moveDown(0.3);
    doc
      .fontSize(9)
      .fillColor('#666')
      .text('BazaarX Marketplace — issued by the seller', { align: 'center' });
    doc.fillColor('#000').moveDown(1);

    // --- Invoice meta ---
    const top = doc.y;
    doc.fontSize(9);
    doc.text(`Invoice No: ${d.invoiceNumber}`, 40, top);
    doc.text(`Invoice Date: ${new Date(d.issuedAt).toLocaleDateString('en-IN')}`, 40, top + 14);
    doc.text(`Order No: ${d.orderNumber}`, 40, top + 28);
    doc.moveDown(2);

    // --- Seller / Buyer blocks ---
    const blockY = doc.y;
    doc.fontSize(10).font('Helvetica-Bold').text('Sold By:', 40, blockY);
    doc.font('Helvetica').fontSize(9);
    doc.text(d.seller.businessName, 40, blockY + 14);
    doc.text(`GSTIN: ${d.seller.gstin}`, 40, blockY + 27);
    doc.text(`State: ${d.seller.stateName}`, 40, blockY + 40);

    doc.fontSize(10).font('Helvetica-Bold').text('Billed To:', 320, blockY);
    doc.font('Helvetica').fontSize(9);
    doc.text(d.buyer.name, 320, blockY + 14);
    doc.text(d.buyer.address, 320, blockY + 27, { width: 230 });
    doc.text(`${d.buyer.state} - ${d.buyer.pincode}`, 320, blockY + 53);
    doc.text(`Place of Supply: ${d.buyer.state}`, 320, blockY + 66);

    doc.moveDown(6);

    // --- Items table ---
    const tableTop = doc.y;
    const cols = d.isIntraState
      ? ['#', 'Item', 'HSN', 'Qty', 'Taxable', 'CGST', 'SGST', 'Total']
      : ['#', 'Item', 'HSN', 'Qty', 'Taxable', 'IGST', '', 'Total'];
    const x = [40, 60, 230, 280, 310, 380, 440, 500];

    doc.font('Helvetica-Bold').fontSize(8);
    cols.forEach((c, i) => doc.text(c, x[i], tableTop, { width: i === 1 ? 165 : 60 }));
    doc.moveTo(40, tableTop + 12).lineTo(555, tableTop + 12).stroke();

    doc.font('Helvetica').fontSize(8);
    let y = tableTop + 18;
    d.lines.forEach((ln, idx) => {
      doc.text(String(idx + 1), x[0], y);
      doc.text(ln.title.slice(0, 40), x[1], y, { width: 165 });
      doc.text(ln.hsnCode, x[2], y);
      doc.text(String(ln.quantity), x[3], y);
      doc.text(rupees(ln.taxableValue), x[4], y, { width: 65 });
      if (d.isIntraState) {
        doc.text(`${rupees(ln.cgst)}`, x[5], y, { width: 55 });
        doc.text(`${rupees(ln.sgst)}`, x[6], y, { width: 55 });
      } else {
        doc.text(`${rupees(ln.igst)}`, x[5], y, { width: 110 });
      }
      doc.text(rupees(ln.lineTotal), x[7], y, { width: 55 });
      y += 16;
    });

    doc.moveTo(40, y).lineTo(555, y).stroke();
    y += 8;

    // --- Totals ---
    doc.font('Helvetica').fontSize(9);
    const label = (t: string, v: string, yy: number, bold = false) => {
      doc.font(bold ? 'Helvetica-Bold' : 'Helvetica');
      doc.text(t, 380, yy, { width: 100 });
      doc.text(v, 480, yy, { width: 75, align: 'right' });
    };
    label('Taxable Value:', rupees(d.taxableValue), y);
    y += 14;
    if (d.isIntraState) {
      label('CGST:', rupees(d.totalCgst), y);
      y += 14;
      label('SGST:', rupees(d.totalSgst), y);
      y += 14;
    } else {
      label('IGST:', rupees(d.totalIgst), y);
      y += 14;
    }
    label('Grand Total:', rupees(d.grandTotal), y, true);

    // --- Footer ---
    doc.font('Helvetica').fontSize(8).fillColor('#888');
    doc.text(
      'This is a computer-generated invoice and does not require a physical signature.',
      40,
      780,
      { align: 'center', width: 515 },
    );
  }
}
