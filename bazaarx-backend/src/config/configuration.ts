/**
 * Centralized, typed application configuration.
 * Loaded once at boot via @nestjs/config and injected everywhere
 * through ConfigService. Keeps env access in ONE place.
 */
export default () => ({
  app: {
    env: process.env.NODE_ENV || 'development',
    name: process.env.APP_NAME || 'BazaarX',
    port: parseInt(process.env.APP_PORT || '3000', 10),
    apiPrefix: process.env.API_PREFIX || 'api',
    apiVersion: process.env.API_VERSION || 'v1',
    corsOrigins: (process.env.CORS_ORIGINS || '').split(',').filter(Boolean),
  },

  postgres: {
    host: process.env.POSTGRES_HOST || 'localhost',
    port: parseInt(process.env.POSTGRES_PORT || '5432', 10),
    username: process.env.POSTGRES_USER || 'bazaarx',
    password: process.env.POSTGRES_PASSWORD || '',
    database: process.env.POSTGRES_DB || 'bazaarx',
    synchronize: process.env.POSTGRES_SYNCHRONIZE === 'true',
    logging: process.env.POSTGRES_LOGGING === 'true',
  },

  mongo: {
    uri: process.env.MONGO_URI || 'mongodb://localhost:27017/bazaarx',
  },

  redis: {
    host: process.env.REDIS_HOST || 'localhost',
    port: parseInt(process.env.REDIS_PORT || '6379', 10),
    password: process.env.REDIS_PASSWORD || undefined,
    db: parseInt(process.env.REDIS_DB || '0', 10),
  },

  elasticsearch: {
    node: process.env.ELASTICSEARCH_NODE || 'http://localhost:9200',
    username: process.env.ELASTICSEARCH_USERNAME || undefined,
    password: process.env.ELASTICSEARCH_PASSWORD || undefined,
  },

  jwt: {
    accessSecret: process.env.JWT_ACCESS_SECRET || 'dev_access_secret',
    accessExpiry: process.env.JWT_ACCESS_EXPIRY || '15m',
    refreshSecret: process.env.JWT_REFRESH_SECRET || 'dev_refresh_secret',
    refreshExpiry: process.env.JWT_REFRESH_EXPIRY || '30d',
  },

  otp: {
    length: parseInt(process.env.OTP_LENGTH || '6', 10),
    expirySeconds: parseInt(process.env.OTP_EXPIRY_SECONDS || '300', 10),
    maxAttempts: parseInt(process.env.OTP_MAX_ATTEMPTS || '5', 10),
    resendCooldownSeconds: parseInt(
      process.env.OTP_RESEND_COOLDOWN_SECONDS || '60',
      10,
    ),
  },

  sms: {
    msg91AuthKey: process.env.MSG91_AUTH_KEY || '',
    msg91SenderId: process.env.MSG91_SENDER_ID || 'BAZRX',
    msg91TemplateId: process.env.MSG91_OTP_TEMPLATE_ID || '',
  },

  google: {
    clientId: process.env.GOOGLE_CLIENT_ID || '',
    clientSecret: process.env.GOOGLE_CLIENT_SECRET || '',
  },

  razorpay: {
    keyId: process.env.RAZORPAY_KEY_ID || '',
    keySecret: process.env.RAZORPAY_KEY_SECRET || '',
    webhookSecret: process.env.RAZORPAY_WEBHOOK_SECRET || '',
  },

  shiprocket: {
    email: process.env.SHIPROCKET_EMAIL || '',
    password: process.env.SHIPROCKET_PASSWORD || '',
    pickupPincode: process.env.SHIPROCKET_PICKUP_PINCODE || '560001',
    pickupLocation: process.env.SHIPROCKET_PICKUP_LOCATION || 'Primary',
    webhookToken: process.env.SHIPROCKET_WEBHOOK_TOKEN || '',
  },

  ondc: {
    subscriberId: process.env.ONDC_SUBSCRIBER_ID || 'bazaarx.example.com',
    subscriberUrl:
      process.env.ONDC_SUBSCRIBER_URL || 'https://bazaarx.example.com/api/v1/ondc',
    uniqueKeyId: process.env.ONDC_UNIQUE_KEY_ID || 'bazaarx-key-1',
    signingPrivateKey: process.env.ONDC_SIGNING_PRIVATE_KEY || '',
    gatewayUrl: process.env.ONDC_GATEWAY_URL || 'https://staging.gateway.ondc.org',
    domain: process.env.ONDC_DOMAIN || 'ONDC:RET10', // retail
    country: process.env.ONDC_COUNTRY || 'IND',
    city: process.env.ONDC_CITY || 'std:080', // Bengaluru
  },

  throttle: {
    ttl: parseInt(process.env.THROTTLE_TTL || '60', 10),
    limit: parseInt(process.env.THROTTLE_LIMIT || '100', 10),
  },
});
