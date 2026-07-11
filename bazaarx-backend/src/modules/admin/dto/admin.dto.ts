import { ApiProperty, ApiPropertyOptional } from '@nestjs/swagger';
import { IsEnum, IsOptional, IsString } from 'class-validator';
import { UserRole } from '../../users/entities/user.entity';
import { PaginationQueryDto } from '../../../common/dto/pagination-query.dto';

export class SetRoleDto {
  @ApiProperty({ enum: UserRole })
  @IsEnum(UserRole)
  role: UserRole;
}

export class AdminUserQueryDto extends PaginationQueryDto {
  @ApiPropertyOptional({ description: 'Search by mobile (partial)' })
  @IsOptional()
  @IsString()
  search?: string;

  @ApiPropertyOptional({ enum: UserRole })
  @IsOptional()
  @IsEnum(UserRole)
  role?: UserRole;
}
