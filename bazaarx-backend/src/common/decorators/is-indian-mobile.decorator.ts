import {
  registerDecorator,
  ValidationOptions,
  ValidationArguments,
} from 'class-validator';

/**
 * Validates a 10-digit Indian mobile number.
 * Accepts optional +91 / 91 / 0 prefixes and normalizes mentally to
 * the 10-digit form starting with 6-9 (valid Indian mobile series).
 *
 * Usage:
 *   @IsIndianMobile()
 *   mobile: string;
 */
export function IsIndianMobile(validationOptions?: ValidationOptions) {
  return function (object: object, propertyName: string) {
    registerDecorator({
      name: 'isIndianMobile',
      target: object.constructor,
      propertyName,
      options: validationOptions,
      validator: {
        validate(value: unknown) {
          if (typeof value !== 'string') return false;
          return /^[6-9]\d{9}$/.test(normalizeIndianMobile(value));
        },
        defaultMessage(args: ValidationArguments) {
          return `${args.property} must be a valid 10-digit Indian mobile number`;
        },
      },
    });
  };
}

/**
 * Normalizes any accepted format to bare 10 digits, length-aware so a
 * genuine 10-digit number starting with "91" is NOT mistaken for a
 * country code:
 *   "+919123456789" / "919123456789" (12) → strip 91
 *   "09123456789"   (11, leading 0)       → strip 0
 *   "9123456789"    (10)                  → unchanged
 */
export function normalizeIndianMobile(value: string): string {
  let v = value.replace(/\s+/g, '').replace(/^\+/, '');
  if (v.length === 12 && v.startsWith('91')) v = v.slice(2);
  else if (v.length === 11 && v.startsWith('0')) v = v.slice(1);
  return v;
}
