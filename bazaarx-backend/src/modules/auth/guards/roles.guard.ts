import { Injectable, CanActivate, ExecutionContext, ForbiddenException } from '@nestjs/common';
import { Reflector } from '@nestjs/core';
import { ROLES_KEY } from '../decorators/roles.decorator';
import { UserRole } from '../../users/entities/user.entity';
import { AuthenticatedUser } from '../decorators/current-user.decorator';

/**
 * Enforces @Roles(...) on top of the global JWT guard.
 * Runs after authentication, so req.user is already populated.
 */
@Injectable()
export class RolesGuard implements CanActivate {
  constructor(private readonly reflector: Reflector) {}

  canActivate(context: ExecutionContext): boolean {
    const required = this.reflector.getAllAndOverride<UserRole[]>(ROLES_KEY, [
      context.getHandler(),
      context.getClass(),
    ]);
    if (!required || required.length === 0) return true;

    const user = context.switchToHttp().getRequest().user as AuthenticatedUser;
    if (!user || !required.includes(user.role as UserRole)) {
      throw new ForbiddenException('Insufficient permissions for this action');
    }
    return true;
  }
}
