import { Injectable, Logger, NotFoundException } from '@nestjs/common';
import { InjectRepository } from '@nestjs/typeorm';
import { Repository } from 'typeorm';
import {
  Notification,
  NotificationType,
} from '../entities/notification.entity';
import { NotificationPreference } from '../entities/notification-preference.entity';
import { User } from '../../users/entities/user.entity';
import { EmailChannel, SmsChannel, PushChannel } from '../channels/channels';
import { paginate } from '../../../common/dto/paginated-result';
import { PaginationQueryDto } from '../../../common/dto/pagination-query.dto';
import { UpdatePreferencesDto } from '../dto/notification.dto';

@Injectable()
export class NotificationService {
  private readonly logger = new Logger('NotificationService');

  constructor(
    @InjectRepository(Notification)
    private readonly notifRepo: Repository<Notification>,
    @InjectRepository(NotificationPreference)
    private readonly prefRepo: Repository<NotificationPreference>,
    @InjectRepository(User)
    private readonly userRepo: Repository<User>,
    private readonly email: EmailChannel,
    private readonly sms: SmsChannel,
    private readonly push: PushChannel,
  ) {}

  /**
   * Core entry point: persists an in-app notification and fans out to
   * the user's enabled external channels. Channel failures are logged,
   * never thrown — a delivery hiccup must not break the triggering flow.
   */
  async notify(params: {
    userId: string;
    type: NotificationType;
    title: string;
    body: string;
    data?: Record<string, unknown>;
  }): Promise<void> {
    const { userId, type, title, body, data } = params;
    try {
      await this.notifRepo.save(
        this.notifRepo.create({ userId, type, title, body, data: data ?? {} }),
      );

      const prefs = await this.getPreferences(userId);
      const user = await this.userRepo.findOne({ where: { id: userId } });

      const tasks: Promise<unknown>[] = [];
      if (prefs.sms) tasks.push(this.sms.send(user?.mobile, `${title}: ${body}`));
      if (prefs.email) tasks.push(this.email.send(user?.email, title, body));
      if (prefs.push) tasks.push(this.push.send(userId, title, body));
      await Promise.allSettled(tasks);
    } catch (err) {
      this.logger.error(
        `Failed to notify ${userId} (${type}): ${(err as Error).message}`,
      );
    }
  }

  // -------- Inbox --------

  async list(userId: string, query: PaginationQueryDto) {
    const [items, total] = await this.notifRepo.findAndCount({
      where: { userId },
      order: { createdAt: 'DESC' },
      skip: query.offset,
      take: query.limit,
    });
    return paginate(
      items,
      total,
      query.page,
      query.limit,
      'Notifications fetched',
    );
  }

  async unreadCount(userId: string): Promise<number> {
    return this.notifRepo.count({ where: { userId, isRead: false } });
  }

  async markRead(userId: string, id: string): Promise<Notification> {
    const notif = await this.notifRepo.findOne({ where: { id, userId } });
    if (!notif) throw new NotFoundException('Notification not found');
    if (!notif.isRead) {
      notif.isRead = true;
      notif.readAt = new Date();
      await this.notifRepo.save(notif);
    }
    return notif;
  }

  async markAllRead(userId: string): Promise<{ updated: number }> {
    const res = await this.notifRepo.update(
      { userId, isRead: false },
      { isRead: true, readAt: new Date() },
    );
    return { updated: res.affected ?? 0 };
  }

  // -------- Preferences --------

  async getPreferences(userId: string): Promise<NotificationPreference> {
    let prefs = await this.prefRepo.findOne({ where: { userId } });
    if (!prefs) {
      prefs = await this.prefRepo.save(this.prefRepo.create({ userId }));
    }
    return prefs;
  }

  async updatePreferences(
    userId: string,
    dto: UpdatePreferencesDto,
  ): Promise<NotificationPreference> {
    const prefs = await this.getPreferences(userId);
    if (dto.sms !== undefined) prefs.sms = dto.sms;
    if (dto.email !== undefined) prefs.email = dto.email;
    if (dto.push !== undefined) prefs.push = dto.push;
    return this.prefRepo.save(prefs);
  }
}
