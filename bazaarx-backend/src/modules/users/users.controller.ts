import {
  Body,
  Controller,
  Get,
  Patch,
  Post,
  Delete,
  Param,
  Version,
  HttpCode,
  HttpStatus,
  ParseUUIDPipe,
} from '@nestjs/common';
import { ApiTags, ApiOperation, ApiBearerAuth } from '@nestjs/swagger';
import { UsersService } from './users.service';
import { AddressService } from './address.service';
import { CurrentUser } from '../auth/decorators/current-user.decorator';
import {
  UpdateProfileDto,
  CreateAddressDto,
  UpdateAddressDto,
} from './dto/user.dto';
import { User } from './entities/user.entity';

@ApiTags('User Profile & Addresses')
@ApiBearerAuth()
@Controller('users')
export class UsersController {
  constructor(
    private readonly users: UsersService,
    private readonly addresses: AddressService,
  ) {}

  // -------- Profile --------

  @Get('me')
  @Version('1')
  @ApiOperation({ summary: 'Get my full profile' })
  async getMe(@CurrentUser('id') userId: string) {
    const user = await this.users.getProfile(userId);
    return { data: this.shapeProfile(user), message: 'Profile fetched' };
  }

  @Patch('me')
  @Version('1')
  @ApiOperation({ summary: 'Update my profile' })
  async updateMe(
    @CurrentUser('id') userId: string,
    @Body() dto: UpdateProfileDto,
  ) {
    const user = await this.users.updateProfile(userId, dto);
    return { data: this.shapeProfile(user), message: 'Profile updated' };
  }

  // -------- Addresses --------

  @Get('me/addresses')
  @Version('1')
  @ApiOperation({ summary: 'List my saved addresses' })
  async listAddresses(@CurrentUser('id') userId: string) {
    const data = await this.addresses.findAllForUser(userId);
    return { data, message: 'Addresses fetched' };
  }

  @Post('me/addresses')
  @Version('1')
  @ApiOperation({ summary: 'Add a new address' })
  async addAddress(
    @CurrentUser('id') userId: string,
    @Body() dto: CreateAddressDto,
  ) {
    const data = await this.addresses.create(userId, dto);
    return { data, message: 'Address added' };
  }

  @Patch('me/addresses/:id')
  @Version('1')
  @ApiOperation({ summary: 'Update an address' })
  async updateAddress(
    @CurrentUser('id') userId: string,
    @Param('id', ParseUUIDPipe) id: string,
    @Body() dto: UpdateAddressDto,
  ) {
    const data = await this.addresses.update(userId, id, dto);
    return { data, message: 'Address updated' };
  }

  @Post('me/addresses/:id/set-default')
  @Version('1')
  @HttpCode(HttpStatus.OK)
  @ApiOperation({ summary: 'Mark an address as default' })
  async setDefault(
    @CurrentUser('id') userId: string,
    @Param('id', ParseUUIDPipe) id: string,
  ) {
    const data = await this.addresses.setDefault(userId, id);
    return { data, message: 'Default address updated' };
  }

  @Delete('me/addresses/:id')
  @Version('1')
  @ApiOperation({ summary: 'Delete an address' })
  async deleteAddress(
    @CurrentUser('id') userId: string,
    @Param('id', ParseUUIDPipe) id: string,
  ) {
    await this.addresses.remove(userId, id);
    return { data: null, message: 'Address deleted' };
  }

  /** Strips internal fields before returning a user to the client. */
  private shapeProfile(user: User) {
    return {
      id: user.id,
      mobile: user.mobile,
      email: user.email ?? null,
      firstName: user.firstName ?? null,
      lastName: user.lastName ?? null,
      fullName: user.fullName,
      dateOfBirth: user.dateOfBirth ?? null,
      gender: user.gender ?? null,
      avatarUrl: user.avatarUrl ?? null,
      preferredLanguage: user.preferredLanguage,
      role: user.role,
      isMobileVerified: user.isMobileVerified,
      isEmailVerified: user.isEmailVerified,
      createdAt: user.createdAt,
    };
  }
}
