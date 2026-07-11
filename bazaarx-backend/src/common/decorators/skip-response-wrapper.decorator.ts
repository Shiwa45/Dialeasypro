import { SetMetadata } from '@nestjs/common';

export const SKIP_RESPONSE_WRAPPER = 'skipResponseWrapper';

/**
 * Marks a route handler whose return value must NOT be wrapped in the
 * standard API envelope — e.g. ONDC/Beckn endpoints that must return the
 * raw protocol payload exactly as the network expects.
 */
export const SkipResponseWrapper = () =>
  SetMetadata(SKIP_RESPONSE_WRAPPER, true);
