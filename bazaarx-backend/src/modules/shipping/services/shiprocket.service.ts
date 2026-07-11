import { Inject, Injectable, Logger } from '@nestjs/common';
import { ConfigService } from '@nestjs/config';
import Redis from 'ioredis';
import { randomBytes } from 'crypto';
import { REDIS_CLIENT } from '../../../database/redis.module';

export interface CourierOption {
  courierName: string;
  courierId: number;
  rate: number; // paise
  estimatedDays: number;
  cod: boolean;
}

export interface CreatedShipment {
  providerOrderId: string;
  providerShipmentId: string;
  awbCode: string;
  courierName: string;
  labelUrl: string;
  trackingUrl: string;
  isMock: boolean;
}

export interface TrackingEvent {
  status: string;
  activity: string;
  location: string;
  timestamp: string;
}

const SR_BASE = 'https://apiv2.shiprocket.in/v1/external';
const TOKEN_KEY = 'shiprocket:token';
const TOKEN_TTL = 9 * 24 * 60 * 60; // ~9 days

/**
 * Shiprocket logistics integration.
 *
 * Real API when SHIPROCKET_EMAIL/PASSWORD are set; otherwise MOCK mode
 * fabricates realistic serviceability, AWB assignment, and tracking so
 * the full flow is testable without a Shiprocket account.
 */
@Injectable()
export class ShiprocketService {
  private readonly logger = new Logger('Shiprocket');

  constructor(
    private readonly config: ConfigService,
    @Inject(REDIS_CLIENT) private readonly redis: Redis,
  ) {}

  get isMock(): boolean {
    return (
      !this.config.get<string>('shiprocket.email') ||
      !this.config.get<string>('shiprocket.password')
    );
  }

  /** Authenticates and caches the token in Redis. */
  private async getToken(): Promise<string> {
    if (this.isMock) return 'MOCK_TOKEN';
    const cached = await this.redis.get(TOKEN_KEY);
    if (cached) return cached;

    const res = await fetch(`${SR_BASE}/auth/login`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        email: this.config.get('shiprocket.email'),
        password: this.config.get('shiprocket.password'),
      }),
    });
    if (!res.ok) throw new Error(`Shiprocket auth failed (${res.status})`);
    const data = (await res.json()) as { token: string };
    await this.redis.set(TOKEN_KEY, data.token, 'EX', TOKEN_TTL);
    return data.token;
  }

  private async authedFetch(path: string, init: RequestInit = {}) {
    const token = await this.getToken();
    return fetch(`${SR_BASE}${path}`, {
      ...init,
      headers: {
        'Content-Type': 'application/json',
        Authorization: `Bearer ${token}`,
        ...(init.headers || {}),
      },
    });
  }

  /** Lists couriers that can service a pickup→delivery lane. */
  async checkServiceability(
    pickup: string,
    delivery: string,
    weightGrams: number,
    cod: boolean,
  ): Promise<CourierOption[]> {
    if (this.isMock) {
      // Deterministic sample couriers; unserviceable for pincodes starting '00'
      if (delivery.startsWith('00')) return [];
      return [
        { courierName: 'Delhivery Surface', courierId: 1, rate: 4500, estimatedDays: 4, cod: true },
        { courierName: 'Bluedart Express', courierId: 2, rate: 8900, estimatedDays: 2, cod },
        { courierName: 'Ekart Logistics', courierId: 3, rate: 3900, estimatedDays: 5, cod: true },
      ];
    }
    const qs = new URLSearchParams({
      pickup_postcode: pickup,
      delivery_postcode: delivery,
      weight: String(weightGrams / 1000),
      cod: cod ? '1' : '0',
    });
    const res = await this.authedFetch(`/courier/serviceability/?${qs}`);
    if (!res.ok) throw new Error(`Serviceability check failed (${res.status})`);
    const data = (await res.json()) as any;
    const couriers = data?.data?.available_courier_companies ?? [];
    return couriers.map((c: any) => ({
      courierName: c.courier_name,
      courierId: c.courier_company_id,
      rate: Math.round((c.rate ?? 0) * 100),
      estimatedDays: Number(c.estimated_delivery_days ?? c.etd ?? 0),
      cod: c.cod === 1 || c.cod === true,
    }));
  }

  /**
   * Creates a Shiprocket order and assigns an AWB in one call.
   * Returns the AWB, courier, and label/tracking URLs.
   */
  async createShipment(params: {
    orderNumber: string;
    pickupPincode: string;
    delivery: { name: string; pincode: string; city: string; state: string; address: string; mobile: string };
    items: Array<{ name: string; sku: string; units: number; sellingPrice: number }>;
    weightGrams: number;
    cod: boolean;
    subTotalPaise: number;
  }): Promise<CreatedShipment> {
    if (this.isMock) {
      const id = randomBytes(5).toString('hex');
      const awb = `MOCKAWB${randomBytes(4).toString('hex').toUpperCase()}`;
      this.logger.debug(`[MOCK] Created shipment for ${params.orderNumber}, AWB ${awb}`);
      return {
        providerOrderId: `srorder_${id}`,
        providerShipmentId: `srship_${id}`,
        awbCode: awb,
        courierName: 'Delhivery Surface (mock)',
        labelUrl: `https://mock.shiprocket/labels/${awb}.pdf`,
        trackingUrl: `https://mock.shiprocket/track/${awb}`,
        isMock: true,
      };
    }

    // 1) create adhoc order
    const createRes = await this.authedFetch('/orders/create/adhoc', {
      method: 'POST',
      body: JSON.stringify({
        order_id: params.orderNumber,
        order_date: new Date().toISOString().slice(0, 10),
        pickup_location: this.config.get('shiprocket.pickupLocation'),
        billing_customer_name: params.delivery.name,
        billing_address: params.delivery.address,
        billing_city: params.delivery.city,
        billing_pincode: params.delivery.pincode,
        billing_state: params.delivery.state,
        billing_country: 'India',
        billing_phone: params.delivery.mobile,
        shipping_is_billing: true,
        order_items: params.items.map((i) => ({
          name: i.name,
          sku: i.sku,
          units: i.units,
          selling_price: i.sellingPrice / 100,
        })),
        payment_method: params.cod ? 'COD' : 'Prepaid',
        sub_total: params.subTotalPaise / 100,
        length: 10,
        breadth: 10,
        height: 10,
        weight: params.weightGrams / 1000,
      }),
    });
    if (!createRes.ok) throw new Error(`SR order create failed (${createRes.status})`);
    const created = (await createRes.json()) as any;

    // 2) assign AWB
    const awbRes = await this.authedFetch('/courier/assign/awb', {
      method: 'POST',
      body: JSON.stringify({ shipment_id: created.shipment_id }),
    });
    if (!awbRes.ok) throw new Error(`AWB assignment failed (${awbRes.status})`);
    const awbData = (await awbRes.json()) as any;
    const resp = awbData?.response?.data ?? {};

    return {
      providerOrderId: String(created.order_id),
      providerShipmentId: String(created.shipment_id),
      awbCode: resp.awb_code,
      courierName: resp.courier_name,
      labelUrl: resp.label_url ?? '',
      trackingUrl: resp.awb_code ? `https://shiprocket.co/tracking/${resp.awb_code}` : '',
      isMock: false,
    };
  }

  /**
   * Creates a reverse (return) pickup from the buyer back to the seller.
   * Mock fabricates an AWB; real mode would call /orders/create/return.
   */
  async createReturnShipment(params: {
    orderNumber: string;
    pickup: { name: string; pincode: string; city: string; state: string; address: string; mobile: string };
    items: Array<{ name: string; sku: string; units: number; sellingPrice: number }>;
    weightGrams: number;
  }): Promise<{ providerShipmentId: string; awbCode: string; isMock: boolean }> {
    if (this.isMock) {
      const awb = `MOCKRET${randomBytes(4).toString('hex').toUpperCase()}`;
      this.logger.debug(
        `[MOCK] Created reverse pickup for ${params.orderNumber}, AWB ${awb}`,
      );
      return {
        providerShipmentId: `srret_${randomBytes(5).toString('hex')}`,
        awbCode: awb,
        isMock: true,
      };
    }
    const res = await this.authedFetch('/orders/create/return', {
      method: 'POST',
      body: JSON.stringify({
        order_id: `RET-${params.orderNumber}`,
        order_date: new Date().toISOString().slice(0, 10),
        pickup_customer_name: params.pickup.name,
        pickup_address: params.pickup.address,
        pickup_city: params.pickup.city,
        pickup_state: params.pickup.state,
        pickup_pincode: params.pickup.pincode,
        pickup_phone: params.pickup.mobile,
        order_items: params.items.map((i) => ({
          name: i.name,
          sku: i.sku,
          units: i.units,
          selling_price: i.sellingPrice / 100,
        })),
        weight: params.weightGrams / 1000,
      }),
    });
    if (!res.ok) throw new Error(`Return shipment failed (${res.status})`);
    const data = (await res.json()) as any;
    return {
      providerShipmentId: String(data.shipment_id),
      awbCode: data.awb_code ?? '',
      isMock: false,
    };
  }

  /** Returns tracking events for an AWB. */
  async track(awb: string): Promise<{ status: string; events: TrackingEvent[] }> {
    if (this.isMock) {
      return {
        status: 'in_transit',
        events: [
          { status: 'PICKED_UP', activity: 'Shipment picked up', location: 'Bengaluru', timestamp: new Date().toISOString() },
          { status: 'IN_TRANSIT', activity: 'In transit to destination', location: 'Hub', timestamp: new Date().toISOString() },
        ],
      };
    }
    const res = await this.authedFetch(`/courier/track/awb/${awb}`);
    if (!res.ok) throw new Error(`Tracking failed (${res.status})`);
    const data = (await res.json()) as any;
    const t = data?.tracking_data ?? {};
    return {
      status: t.shipment_status ?? 'unknown',
      events: (t.shipment_track_activities ?? []).map((a: any) => ({
        status: a.status,
        activity: a.activity,
        location: a.location,
        timestamp: a.date,
      })),
    };
  }
}
