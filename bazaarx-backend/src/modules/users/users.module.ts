import { Module } from '@nestjs/common';
import { TypeOrmModule } from '@nestjs/typeorm';
import { User } from './entities/user.entity';
import { Address } from './entities/address.entity';
import { UsersService } from './users.service';
import { AddressService } from './address.service';
import { UsersController } from './users.controller';

@Module({
  imports: [TypeOrmModule.forFeature([User, Address])],
  controllers: [UsersController],
  providers: [UsersService, AddressService],
  exports: [UsersService, AddressService, TypeOrmModule],
})
export class UsersModule {}
