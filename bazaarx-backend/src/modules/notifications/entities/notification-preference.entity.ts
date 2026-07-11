import { Entity, Column, Index } from 'typeorm';
import { BaseEntity } from '../../../common/entities/base.entity';

/**
 * Per-user channel toggles. In-app is always on (the inbox); the others
 * gate external dispatch. Defaults to everything enabled.
 */
@Entity('notification_preferences')
export class NotificationPreference extends BaseEntity {
  @Index({ unique: true })
  @Column({ type: 'uuid', unique: true })
  userId: string;

  @Column({ type: 'boolean', default: true })
  sms: boolean;

  @Column({ type: 'boolean', default: true })
  email: boolean;

  @Column({ type: 'boolean', default: true })
  push: boolean;
}
