import {
  Body,
  Controller,
  Post,
  Get,
  Version,
  HttpCode,
  HttpStatus,
} from '@nestjs/common';
import { ApiTags, ApiOperation } from '@nestjs/swagger';
import { OndcBppService } from '../services/ondc-bpp.service';
import { BecknContextService } from '../services/beckn-context.service';
import { OndcCatalogService } from '../services/ondc-catalog.service';
import { Public } from '../../auth/decorators/public.decorator';
import { SkipResponseWrapper } from '../../../common/decorators/skip-response-wrapper.decorator';
import { BecknEnvelope } from '../types/beckn.types';

/**
 * ONDC (Beckn) BPP endpoints. These are called by the ONDC gateway /
 * buyer apps, so they're public + signature-authenticated at the network
 * layer (the auth header is built/verified by BecknContextService). The
 * adapter returns on_* payloads synchronously for testability.
 */
@ApiTags('ONDC (Beckn)')
@Public()
@Controller('ondc')
export class OndcController {
  constructor(
    private readonly bpp: OndcBppService,
    private readonly ctx: BecknContextService,
    private readonly catalog: OndcCatalogService,
  ) {}

  @Get('health')
  @Version('1')
  @ApiOperation({ summary: 'ONDC adapter status' })
  health() {
    return {
      data: {
        subscriberId: this.ctx.subscriberId,
        mode: this.ctx.isMock ? 'mock (unsigned)' : 'live (signed)',
        role: 'BPP',
      },
      message: 'ONDC adapter',
    };
  }

  @Post('search')
  @Version('1')
  @HttpCode(HttpStatus.OK)
  @SkipResponseWrapper()
  @ApiOperation({ summary: 'Beckn /search → on_search catalog' })
  search(@Body() env: BecknEnvelope<any>) {
    return this.bpp.onSearch(env);
  }

  @Post('select')
  @Version('1')
  @HttpCode(HttpStatus.OK)
  @SkipResponseWrapper()
  @ApiOperation({ summary: 'Beckn /select → on_select quote' })
  select(@Body() env: BecknEnvelope<any>) {
    return this.bpp.onSelect(env);
  }

  @Post('init')
  @Version('1')
  @HttpCode(HttpStatus.OK)
  @SkipResponseWrapper()
  @ApiOperation({ summary: 'Beckn /init → on_init quote + payment' })
  init(@Body() env: BecknEnvelope<any>) {
    return this.bpp.onInit(env);
  }

  @Post('confirm')
  @Version('1')
  @HttpCode(HttpStatus.OK)
  @SkipResponseWrapper()
  @ApiOperation({ summary: 'Beckn /confirm → on_confirm order' })
  confirm(@Body() env: BecknEnvelope<any>) {
    return this.bpp.onConfirm(env);
  }

  @Post('status')
  @Version('1')
  @HttpCode(HttpStatus.OK)
  @SkipResponseWrapper()
  @ApiOperation({ summary: 'Beckn /status → on_status order state' })
  status(@Body() env: BecknEnvelope<any>) {
    return this.bpp.onStatus(env);
  }
}
