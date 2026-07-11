import { Entity, Column, ManyToOne, Index, JoinColumn } from 'typeorm';
import { BaseEntity } from '../../../common/entities/base.entity';
import { User } from './user.entity';

/** Address type label for quick selection at checkout. */
export enum AddressLabel {
  HOME = 'home',
  WORK = 'work',
  OTHER = 'other',
}

@Entity('addresses')
export class Address extends BaseEntity {
  @Index()
  @ManyToOne(() => User, { onDelete: 'CASCADE', nullable: false })
  @JoinColumn({ name: 'userId' })
  user: User;

  @Column({ type: 'uuid' })
  userId: string;

  @Column({ type: 'enum', enum: AddressLabel, default: AddressLabel.HOME })
  label: AddressLabel;

  // Recipient details (may differ from the account holder)
  @Column({ type: 'varchar', length: 100 })
  name: string;

  @Column({ type: 'varchar', length: 10 })
  mobile: string;

  @Column({ type: 'varchar', length: 255 })
  line1: string;

  @Column({ type: 'varchar', length: 255, nullable: true })
  line2?: string;

  @Column({ type: 'varchar', length: 100 })
  city: string;

  @Column({ type: 'varchar', length: 100 })
  state: string;

  @Index()
  @Column({ type: 'varchar', length: 6 })
  pincode: string;

  @Column({ type: 'varchar', length: 255, nullable: true })
  landmark?: string;

  // GPS coordinates for precise delivery / map pin
  @Column({ type: 'decimal', precision: 10, scale: 7, nullable: true })
  latitude?: number;

  @Column({ type: 'decimal', precision: 10, scale: 7, nullable: true })
  longitude?: number;

  @Column({ type: 'boolean', default: false })
  isDefault: boolean;
}
