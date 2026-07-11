import { Module, NestModule, MiddlewareConsumer } from '@nestjs/common';
import { ConfigModule, ConfigService } from '@nestjs/config';
import { ThrottlerModule } from '@nestjs/throttler';
import { LoggerModule } from 'nestjs-pino';
import { EventEmitterModule } from '@nestjs/event-emitter';
import configuration from './config/configuration';
import { validateEnv } from './config/env.validation';
import { RequestIdMiddleware } from './common/middleware/request-id.middleware';
import { DatabaseModule } from './database/database.module';
import { HealthModule } from './modules/health/health.module';
import { UsersModule } from './modules/users/users.module';
import { AuthModule } from './modules/auth/auth.module';
import { CatalogModule } from './modules/catalog/catalog.module';
import { SellersModule } from './modules/sellers/sellers.module';
import { SearchModule } from './modules/search/search.module';
import { CartModule } from './modules/cart/cart.module';
import { OrdersModule } from './modules/orders/orders.module';
import { PaymentsModule } from './modules/payments/payments.module';
import { InvoicesModule } from './modules/invoices/invoices.module';
import { ShippingModule } from './modules/shipping/shipping.module';
import { ReturnsModule } from './modules/returns/returns.module';
import { PromotionsModule } from './modules/promotions/promotions.module';
import { ReviewsModule } from './modules/reviews/reviews.module';
import { NotificationsModule } from './modules/notifications/notifications.module';
import { SellerDashboardModule } from './modules/seller-dashboard/seller-dashboard.module';
import { WalletModule } from './modules/wallet/wallet.module';
import { RecommendationsModule } from './modules/recommendations/recommendations.module';
import { AdminModule } from './modules/admin/admin.module';
import { OndcModule } from './modules/ondc/ondc.module';

@Module({
  imports: [
    // --- Global typed config, validated at boot ---
    ConfigModule.forRoot({
      isGlobal: true,
      load: [configuration],
      validate: validateEnv,
      envFilePath: '.env',
    }),

    // --- Structured logging (pino), pretty in dev / JSON in prod ---
    LoggerModule.forRootAsync({
      inject: [ConfigService],
      useFactory: (config: ConfigService) => ({
        pinoHttp: {
          level: config.get('app.env') === 'production' ? 'info' : 'debug',
          transport:
            config.get('app.env') !== 'production'
              ? { target: 'pino-pretty', options: { singleLine: true } }
              : undefined,
          // Never log sensitive fields
          redact: ['req.headers.authorization', 'req.body.password', 'req.body.otp'],
        },
      }),
    }),

    // --- Event bus (decouples modules, e.g. catalogue → search) ---
    EventEmitterModule.forRoot(),

    // --- Global rate limiting ---
    ThrottlerModule.forRootAsync({
      inject: [ConfigService],
      useFactory: (config: ConfigService) => ({
        throttlers: [
          {
            ttl: Number(config.get('throttle.ttl')) * 1000,
            limit: Number(config.get('throttle.limit')),
          },
        ],
      }),
    }),

    // --- Database connections (Postgres, Mongo, Redis, Elasticsearch) ---
    DatabaseModule,

    // --- Feature modules ---
    UsersModule,
    AuthModule,
    CatalogModule,
    SellersModule,
    SearchModule,
    CartModule,
    OrdersModule,
    PaymentsModule,
    InvoicesModule,
    ShippingModule,
    ReturnsModule,
    PromotionsModule,
    ReviewsModule,
    NotificationsModule,
    SellerDashboardModule,
    WalletModule,
    RecommendationsModule,
    AdminModule,
    OndcModule,
    HealthModule,
  ],
})
export class AppModule implements NestModule {
  configure(consumer: MiddlewareConsumer) {
    // Assign a trace ID to every request before guards run
    consumer.apply(RequestIdMiddleware).forRoutes('*');
  }
}
