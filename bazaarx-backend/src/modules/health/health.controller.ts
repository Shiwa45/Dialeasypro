import { Controller, Get, Version, HttpCode, HttpStatus } from '@nestjs/common';
import { ApiTags, ApiOperation } from '@nestjs/swagger';
import { ConfigService } from '@nestjs/config';
import { HealthService } from './health.service';
import { Public } from '../auth/decorators/public.decorator';

@ApiTags('Health')
@Controller('health')
export class HealthController {
  constructor(
    private readonly config: ConfigService,
    private readonly health: HealthService,
  ) {}

  /** Liveness: is the process alive? (fast, no DB calls) */
  @Public()
  @Get()
  @Version('1')
  @ApiOperation({ summary: 'Liveness probe — is the service up?' })
  liveness() {
    // Raw return → ResponseInterceptor wraps in standard envelope
    return {
      data: {
        status: 'ok',
        service: this.config.get('app.name'),
        env: this.config.get('app.env'),
        timestamp: new Date().toISOString(),
        uptime: Math.floor(process.uptime()),
      },
      message: 'Service is alive',
    };
  }

  /** Readiness: are all dependencies reachable? (pings every DB) */
  @Public()
  @Get('ready')
  @Version('1')
  @HttpCode(HttpStatus.OK)
  @ApiOperation({ summary: 'Readiness probe — are all databases reachable?' })
  async readiness() {
    const result = await this.health.checkAll();
    return {
      data: result,
      message: result.healthy
        ? 'All dependencies healthy'
        : 'One or more dependencies are down',
    };
  }
}
