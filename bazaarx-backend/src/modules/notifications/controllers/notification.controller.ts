import {
  Body,
  Controller,
  Get,
  Post,
  Patch,
  Param,
  Query,
  Version,
  ParseUUIDPipe,
  HttpCode,
  HttpStatus,
} from '@nestjs/common';
import { ApiTags, ApiOperation, ApiBearerAuth } from '@nestjs/swagger';
import { NotificationService } from '../services/notification.service';
import { UpdatePreferencesDto } from '../dto/notification.dto';
import { CurrentUser } from '../../auth/decorators/current-user.decorator';
import { PaginationQueryDto } from '../../../common/dto/pagination-query.dto';

@ApiTags('Notifications')
@ApiBearerAuth()
@Controller('notifications')
export class NotificationController {
  constructor(private readonly notifications: NotificationService) {}

  @Get()
  @Version('1')
  @ApiOperation({ summary: 'List my notifications' })
  list(
    @CurrentUser('id') userId: string,
    @Query() query: PaginationQueryDto,
  ) {
    return this.notifications.list(userId, query);
  }

  @Get('unread-count')
  @Version('1')
  @ApiOperation({ summary: 'My unread notification count' })
  async unread(@CurrentUser('id') userId: string) {
    const count = await this.notifications.unreadCount(userId);
    return { data: { count }, message: 'Unread count' };
  }

  @Patch(':id/read')
  @Version('1')
  @ApiOperation({ summary: 'Mark a notification read' })
  async read(
    @CurrentUser('id') userId: string,
    @Param('id', ParseUUIDPipe) id: string,
  ) {
    const data = await this.notifications.markRead(userId, id);
    return { data, message: 'Marked read' };
  }

  @Post('read-all')
  @Version('1')
  @HttpCode(HttpStatus.OK)
  @ApiOperation({ summary: 'Mark all notifications read' })
  async readAll(@CurrentUser('id') userId: string) {
    const data = await this.notifications.markAllRead(userId);
    return { data, message: 'All marked read' };
  }

  @Get('preferences')
  @Version('1')
  @ApiOperation({ summary: 'Get my notification preferences' })
  async getPrefs(@CurrentUser('id') userId: string) {
    const data = await this.notifications.getPreferences(userId);
    return { data, message: 'Preferences' };
  }

  @Patch('preferences')
  @Version('1')
  @ApiOperation({ summary: 'Update my notification channel preferences' })
  async updatePrefs(
    @CurrentUser('id') userId: string,
    @Body() dto: UpdatePreferencesDto,
  ) {
    const data = await this.notifications.updatePreferences(userId, dto);
    return { data, message: 'Preferences updated' };
  }
}
