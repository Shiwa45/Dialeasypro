import { ApiProperty } from '@nestjs/swagger';
import { Type } from 'class-transformer';
import { IsUUID, IsInt, Min, Max } from 'class-validator';

export class AddCartItemDto {
  @ApiProperty({ description: 'Product variant to add' })
  @IsUUID()
  variantId: string;

  @ApiProperty({ example: 1, minimum: 1, maximum: 10 })
  @Type(() => Number)
  @IsInt()
  @Min(1)
  @Max(10) // per-item cap to deter hoarding/bots
  quantity: number;
}

export class UpdateCartItemDto {
  @ApiProperty({ example: 2, minimum: 1, maximum: 10 })
  @Type(() => Number)
  @IsInt()
  @Min(1)
  @Max(10)
  quantity: number;
}
