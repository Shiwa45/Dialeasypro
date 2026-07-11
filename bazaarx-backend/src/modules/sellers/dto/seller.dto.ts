import { ApiProperty, ApiPropertyOptional } from '@nestjs/swagger';
import { Type } from 'class-transformer';
import {
  IsString,
  IsOptional,
  IsEnum,
  IsArray,
  IsUrl,
  Length,
  ValidateNested,
  ArrayMinSize,
} from 'class-validator';
import { BusinessType } from '../entities/seller.entity';
import { DocumentType } from '../entities/seller-document.entity';
import {
  IsGstin,
  IsPan,
  IsIfsc,
} from '../../../common/decorators/is-gst-pan.decorator';

export class SellerDocumentDto {
  @ApiProperty({ enum: DocumentType })
  @IsEnum(DocumentType)
  type: DocumentType;

  @ApiProperty({ example: 'https://cdn.bazaarx.com/kyc/abc.pdf' })
  @IsUrl()
  fileUrl: string;
}

export class RegisterSellerDto {
  @ApiProperty({ example: 'Ravi Electronics Store' })
  @IsString()
  @Length(2, 200)
  displayName: string;

  @ApiProperty({ example: 'Ravi Enterprises Pvt Ltd' })
  @IsString()
  @Length(2, 200)
  businessName: string;

  @ApiProperty({ enum: BusinessType })
  @IsEnum(BusinessType)
  businessType: BusinessType;

  @ApiProperty({ example: '29ABCDE1234F1Z5' })
  @IsGstin()
  gstin: string;

  @ApiProperty({ example: 'ABCDE1234F' })
  @IsPan()
  pan: string;

  @ApiProperty({ example: 'Ravi Kumar' })
  @IsString()
  @Length(2, 150)
  bankAccountHolder: string;

  @ApiProperty({ example: '50100123456789' })
  @IsString()
  @Length(6, 20)
  bankAccountNumber: string;

  @ApiProperty({ example: 'HDFC0001234' })
  @IsIfsc()
  bankIfsc: string;

  @ApiProperty({ type: [SellerDocumentDto], description: 'KYC documents' })
  @IsArray()
  @ArrayMinSize(1)
  @ValidateNested({ each: true })
  @Type(() => SellerDocumentDto)
  documents: SellerDocumentDto[];
}

export class UpdateSellerDto {
  @ApiPropertyOptional()
  @IsOptional()
  @IsString()
  @Length(2, 200)
  displayName?: string;

  @ApiPropertyOptional()
  @IsOptional()
  @IsString()
  @Length(2, 150)
  bankAccountHolder?: string;

  @ApiPropertyOptional()
  @IsOptional()
  @IsString()
  @Length(6, 20)
  bankAccountNumber?: string;

  @ApiPropertyOptional()
  @IsOptional()
  @IsIfsc()
  bankIfsc?: string;
}

export class RejectSellerDto {
  @ApiProperty({ example: 'GST certificate is illegible' })
  @IsString()
  @Length(3, 500)
  reason: string;
}
