import { Entity, Column, Index, ManyToOne, JoinColumn } from 'typeorm';
import { BaseEntity } from '../../../common/entities/base.entity';
import { Seller } from './seller.entity';

export enum DocumentType {
  GST_CERTIFICATE = 'gst_certificate',
  PAN_CARD = 'pan_card',
  AADHAAR = 'aadhaar',
  BANK_PROOF = 'bank_proof', // cancelled cheque / passbook
  FSSAI = 'fssai', // food sellers
}

export enum DocumentStatus {
  PENDING = 'pending',
  VERIFIED = 'verified',
  REJECTED = 'rejected',
}

/**
 * A KYC document submitted by a seller. The actual file is uploaded
 * to object storage (S3) by the client; we store the resulting URL
 * plus verification status. No raw documents pass through the API.
 */
@Entity('seller_documents')
export class SellerDocument extends BaseEntity {
  @Index()
  @ManyToOne(() => Seller, (s) => s.documents, {
    onDelete: 'CASCADE',
    nullable: false,
  })
  @JoinColumn({ name: 'sellerId' })
  seller: Seller;

  @Column({ type: 'uuid' })
  sellerId: string;

  @Column({ type: 'enum', enum: DocumentType })
  type: DocumentType;

  @Column({ type: 'varchar', length: 1000 })
  fileUrl: string;

  @Column({ type: 'enum', enum: DocumentStatus, default: DocumentStatus.PENDING })
  status: DocumentStatus;

  @Column({ type: 'varchar', length: 500, nullable: true })
  rejectionReason?: string;
}
