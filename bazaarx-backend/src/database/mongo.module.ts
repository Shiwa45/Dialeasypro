import { Module } from '@nestjs/common';
import { MongooseModule } from '@nestjs/mongoose';
import { ConfigModule, ConfigService } from '@nestjs/config';

/**
 * MongoDB connection via Mongoose.
 *
 * Used for high-write, schema-flexible data:
 * activity logs, product specs, cart sessions, CMS content,
 * search query logs, notification delivery logs.
 */
@Module({
  imports: [
    MongooseModule.forRootAsync({
      imports: [ConfigModule],
      inject: [ConfigService],
      useFactory: (config: ConfigService) => ({
        uri: config.get<string>('mongo.uri'),
        // Pool + timeout tuning for production
        maxPoolSize: 20,
        serverSelectionTimeoutMS: 5000,
        socketTimeoutMS: 45000,
        // Retry connection a few times, but don't hang boot forever
        retryAttempts: 3,
        retryDelay: 2000,
      }),
    }),
  ],
})
export class MongoModule {}
