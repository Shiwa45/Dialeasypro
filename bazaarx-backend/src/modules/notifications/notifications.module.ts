import { Module } from '@nestjs/common';
import { TypeOrmModule } from '@nestjs/typeorm';
import { Notification } from './entities/notification.entity';
import { NotificationPreference } from './entities/notification-preference.entity';
import { User } from '../users/entities/user.entity';
import { NotificationService } from './services/notification.service';
import { NotificationListener } from './listeners/notification.listener';
import { NotificationController } from './controllers/notification.controller';
import { EmailChannel, SmsChannel, PushChannel } from './channels/channels';

/**
 * Notifications. Listens to lifecycle events on the global bus and fans
 * them out to the in-app inbox plus preference-gated SMS/email/push.
 */
@Module({
  imports: [
    TypeOrmModule.forFeature([Notification, NotificationPreference, User]),
  ],
  controllers: [NotificationController],
  providers: [
    NotificationService,
    NotificationListener,
    EmailChannel,
    SmsChannel,
    PushChannel,
  ],
  exports: [NotificationService],
})
export class NotificationsModule {}
