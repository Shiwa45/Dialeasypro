import { ApiProperty, ApiPropertyOptional } from '@nestjs/swagger';
import { IsUUID, IsEnum, IsOptional, IsString, Length } from 'class-validator';
import { ReturnReason } from '../entities/return.entity';

export class RequestReturnDto {
  @ApiProperty({ description: 'The delivered order item to return' })
  @IsUUID()
  orderItemId: string;

  @ApiProperty({ enum: ReturnReason })
  @IsEnum(ReturnReason)
  reason: ReturnReason;

  @ApiPropertyOptional()
  @IsOptional()
  @IsString()
  @Length(0, 1000)
  comments?: string;
}

export class RejectReturnDto {
  @ApiProperty({ example: 'Item shows signs of use' })
  @IsString()
  @Length(3, 500)
  reason: string;
}
