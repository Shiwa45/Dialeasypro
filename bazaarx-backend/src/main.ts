import { NestFactory, Reflector } from '@nestjs/core';
import { ValidationPipe, VersioningType } from '@nestjs/common';
import { ConfigService } from '@nestjs/config';
import { DocumentBuilder, SwaggerModule } from '@nestjs/swagger';
import { Logger } from 'nestjs-pino';
import helmet from 'helmet';
import { AppModule } from './app.module';
import { AllExceptionsFilter } from './common/filters/all-exceptions.filter';
import { ResponseInterceptor } from './common/interceptors/response.interceptor';

async function bootstrap() {
  const app = await NestFactory.create(AppModule, { bufferLogs: true, rawBody: true });

  // Structured JSON logging (pino) — replaces default Nest logger
  app.useLogger(app.get(Logger));

  const config = app.get(ConfigService);
  const appConfig = config.get('app');

  // --- Security headers ---
  app.use(helmet());

  // --- CORS ---
  app.enableCors({
    origin: appConfig.corsOrigins.length ? appConfig.corsOrigins : '*',
    credentials: true,
  });

  // --- Global route prefix: /api ---
  app.setGlobalPrefix(appConfig.apiPrefix);

  // --- URI versioning: /api/v1/... ---
  app.enableVersioning({
    type: VersioningType.URI,
    defaultVersion: '1',
  });

  // --- Global input validation ---
  app.useGlobalPipes(
    new ValidationPipe({
      whitelist: true, // strip unknown properties
      forbidNonWhitelisted: true, // reject unknown properties
      transform: true, // auto-transform payloads to DTO instances
      transformOptions: { enableImplicitConversion: true },
    }),
  );

  // --- Global error handling (standardized error envelope) ---
  app.useGlobalFilters(new AllExceptionsFilter());

  // --- Global response envelope interceptor ---
  // (request-id is handled earlier via RequestIdMiddleware)
  app.useGlobalInterceptors(new ResponseInterceptor(app.get(Reflector)));

  // --- Graceful shutdown (close DB connections cleanly) ---
  app.enableShutdownHooks();

  // --- Swagger API docs (disabled in production) ---
  if (appConfig.env !== 'production') {
    const swaggerConfig = new DocumentBuilder()
      .setTitle('BazaarX API')
      .setDescription('Multivendor E-commerce Platform API')
      .setVersion('1.0')
      .addBearerAuth()
      .build();
    const document = SwaggerModule.createDocument(app, swaggerConfig);
    SwaggerModule.setup('docs', app, document);
  }

  await app.listen(appConfig.port);

  const logger = app.get(Logger);
  logger.log(
    `🚀 ${appConfig.name} running on http://localhost:${appConfig.port}/${appConfig.apiPrefix}/v1`,
  );
  if (appConfig.env !== 'production') {
    logger.log(`📚 API docs at http://localhost:${appConfig.port}/docs`);
  }
}
bootstrap();
