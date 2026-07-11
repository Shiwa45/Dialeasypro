import { Injectable, NotFoundException, ConflictException } from '@nestjs/common';
import { InjectRepository } from '@nestjs/typeorm';
import { Repository } from 'typeorm';
import { User, UserRole } from './entities/user.entity';

/**
 * User persistence operations needed by auth and other modules.
 * Keeps all User DB access in one place.
 */
@Injectable()
export class UsersService {
  constructor(
    @InjectRepository(User)
    private readonly userRepo: Repository<User>,
  ) {}

  findByMobile(mobile: string): Promise<User | null> {
    return this.userRepo.findOne({ where: { mobile } });
  }

  findByEmail(email: string): Promise<User | null> {
    return this.userRepo.findOne({ where: { email } });
  }

  findById(id: string): Promise<User | null> {
    return this.userRepo.findOne({ where: { id } });
  }

  /** Loads a user WITH the password hash (normally excluded). */
  findByMobileWithPassword(mobile: string): Promise<User | null> {
    return this.userRepo
      .createQueryBuilder('user')
      .addSelect('user.passwordHash')
      .where('user.mobile = :mobile', { mobile })
      .getOne();
  }

  async create(data: {
    mobile: string;
    email?: string;
    firstName?: string;
    lastName?: string;
    passwordHash?: string;
    role?: UserRole;
    isMobileVerified?: boolean;
  }): Promise<User> {
    const user = this.userRepo.create(data);
    return this.userRepo.save(user);
  }

  async markMobileVerified(id: string): Promise<void> {
    await this.userRepo.update(id, { isMobileVerified: true });
  }

  /** Changes a user's role (e.g. buyer → seller on seller approval). */
  async setRole(id: string, role: UserRole): Promise<void> {
    await this.userRepo.update(id, { role });
  }

  async updateLastLogin(id: string): Promise<void> {
    await this.userRepo.update(id, { lastLoginAt: new Date() });
  }

  /** Returns the full user record (safe fields) for the profile screen. */
  async getProfile(id: string): Promise<User> {
    const user = await this.findById(id);
    if (!user) throw new NotFoundException('User not found');
    return user;
  }

  /** Updates editable profile fields, guarding email uniqueness. */
  async updateProfile(
    id: string,
    data: Partial<
      Pick<
        User,
        | 'firstName'
        | 'lastName'
        | 'email'
        | 'dateOfBirth'
        | 'gender'
        | 'preferredLanguage'
        | 'avatarUrl'
      >
    >,
  ): Promise<User> {
    const user = await this.getProfile(id);

    if (data.email && data.email !== user.email) {
      const existing = await this.findByEmail(data.email);
      if (existing && existing.id !== id) {
        throw new ConflictException('Email already in use');
      }
      // Changing email resets verification
      user.isEmailVerified = false;
    }

    Object.assign(user, data);
    return this.userRepo.save(user);
  }
}
