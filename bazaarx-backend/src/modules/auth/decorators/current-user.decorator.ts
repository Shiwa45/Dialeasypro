import { createParamDecorator, ExecutionContext } from '@nestjs/common';

export interface AuthenticatedUser {
  id: string;
  role: string;
}

/**
 * Injects the authenticated user (set by JwtStrategy) into a handler.
 * Usage: myRoute(@CurrentUser() user: AuthenticatedUser)
 * Pass a field name to get just that field: @CurrentUser('id') userId: string
 */
export const CurrentUser = createParamDecorator(
  (field: keyof AuthenticatedUser | undefined, ctx: ExecutionContext) => {
    const request = ctx.switchToHttp().getRequest();
    const user = request.user as AuthenticatedUser;
    return field ? user?.[field] : user;
  },
);
