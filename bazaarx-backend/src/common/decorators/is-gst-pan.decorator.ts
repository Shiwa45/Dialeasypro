import {
  registerDecorator,
  ValidationOptions,
  ValidationArguments,
} from 'class-validator';

/**
 * Validates an Indian GSTIN (15 chars):
 *   2-digit state + 10-char PAN + entity digit + 'Z' + checksum.
 * e.g. 29ABCDE1234F1Z5
 */
export function IsGstin(validationOptions?: ValidationOptions) {
  return function (object: object, propertyName: string) {
    registerDecorator({
      name: 'isGstin',
      target: object.constructor,
      propertyName,
      options: validationOptions,
      validator: {
        validate(value: unknown) {
          if (typeof value !== 'string') return false;
          return /^[0-9]{2}[A-Z]{5}[0-9]{4}[A-Z][1-9A-Z]Z[0-9A-Z]$/.test(
            value.toUpperCase(),
          );
        },
        defaultMessage(args: ValidationArguments) {
          return `${args.property} must be a valid 15-character GSTIN`;
        },
      },
    });
  };
}

/**
 * Validates an Indian PAN (10 chars): 5 letters + 4 digits + 1 letter.
 * e.g. ABCDE1234F
 */
export function IsPan(validationOptions?: ValidationOptions) {
  return function (object: object, propertyName: string) {
    registerDecorator({
      name: 'isPan',
      target: object.constructor,
      propertyName,
      options: validationOptions,
      validator: {
        validate(value: unknown) {
          if (typeof value !== 'string') return false;
          return /^[A-Z]{5}[0-9]{4}[A-Z]$/.test(value.toUpperCase());
        },
        defaultMessage(args: ValidationArguments) {
          return `${args.property} must be a valid 10-character PAN`;
        },
      },
    });
  };
}

/**
 * Validates an Indian bank IFSC code (11 chars):
 *   4 letters + '0' + 6 alphanumerics. e.g. HDFC0001234
 */
export function IsIfsc(validationOptions?: ValidationOptions) {
  return function (object: object, propertyName: string) {
    registerDecorator({
      name: 'isIfsc',
      target: object.constructor,
      propertyName,
      options: validationOptions,
      validator: {
        validate(value: unknown) {
          if (typeof value !== 'string') return false;
          return /^[A-Z]{4}0[A-Z0-9]{6}$/.test(value.toUpperCase());
        },
        defaultMessage(args: ValidationArguments) {
          return `${args.property} must be a valid 11-character IFSC code`;
        },
      },
    });
  };
}
