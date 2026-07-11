import { Entity, Column, Index } from 'typeorm';
import { BaseEntity } from '../../../common/entities/base.entity';

/**
 * A user account. Mobile is the primary identity in India
 * (OTP-first), email is optional. Password is optional too —
 * users can be OTP-only and never set one.
 */
export enum UserRole {
  BUYER = 'buyer',
  SELLER = 'seller',
  ADMIN = 'admin',
}

export enum Gender {
  MALE = 'male',
  FEMALE = 'female',
  OTHER = 'other',
  UNDISCLOSED = 'prefer_not_to_say',
}

/** Supported UI/content languages (India-first). */
export enum Language {
  ENGLISH = 'en',
  HINDI = 'hi',
  TAMIL = 'ta',
  TELUGU = 'te',
  BENGALI = 'bn',
  MARATHI = 'mr',
  KANNADA = 'kn',
  GUJARATI = 'gu',
  MALAYALAM = 'ml',
}

@Entity('users')
export class User extends BaseEntity {
  @Index({ unique: true })
  @Column({ type: 'varchar', length: 10, unique: true })
  mobile: string; // normalized 10-digit Indian number

  @Index({ unique: true, where: 'email IS NOT NULL' })
  @Column({ type: 'varchar', length: 255, nullable: true })
  email?: string;

  // Hashed (bcrypt). Null for OTP-only users. Never returned in API responses.
  @Column({ type: 'varchar', length: 255, nullable: true, select: false })
  passwordHash?: string;

  @Column({ type: 'varchar', length: 100, nullable: true })
  firstName?: string;

  @Column({ type: 'varchar', length: 100, nullable: true })
  lastName?: string;

  @Column({ type: 'date', nullable: true })
  dateOfBirth?: string;

  @Column({ type: 'enum', enum: Gender, nullable: true })
  gender?: Gender;

  @Column({ type: 'varchar', length: 500, nullable: true })
  avatarUrl?: string;

  @Column({
    type: 'enum',
    enum: Language,
    default: Language.ENGLISH,
  })
  preferredLanguage: Language;

  @Column({
    type: 'enum',
    enum: UserRole,
    default: UserRole.BUYER,
  })
  role: UserRole;

  @Column({ type: 'boolean', default: false })
  isMobileVerified: boolean;

  @Column({ type: 'boolean', default: false })
  isEmailVerified: boolean;

  @Column({ type: 'boolean', default: true })
  isActive: boolean;

  @Column({ type: 'timestamptz', nullable: true })
  lastLoginAt?: Date;

  get fullName(): string {
    return [this.firstName, this.lastName].filter(Boolean).join(' ').trim();
  }
}
