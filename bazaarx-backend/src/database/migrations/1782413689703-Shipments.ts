import { MigrationInterface, QueryRunner } from "typeorm";

export class Shipments1782413689703 implements MigrationInterface {
    name = 'Shipments1782413689703'

    public async up(queryRunner: QueryRunner): Promise<void> {
        await queryRunner.query(`CREATE TYPE "public"."shipments_status_enum" AS ENUM('created', 'awb_assigned', 'pickup_scheduled', 'in_transit', 'out_for_delivery', 'delivered', 'rto', 'cancelled')`);
        await queryRunner.query(`CREATE TABLE "shipments" ("id" uuid NOT NULL DEFAULT uuid_generate_v4(), "createdAt" TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT now(), "updatedAt" TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT now(), "deletedAt" TIMESTAMP WITH TIME ZONE, "orderId" uuid NOT NULL, "sellerId" uuid NOT NULL, "providerOrderId" character varying(100), "providerShipmentId" character varying(100), "awbCode" character varying(100), "courierName" character varying(120), "status" "public"."shipments_status_enum" NOT NULL DEFAULT 'created', "pickupPincode" character varying(6) NOT NULL, "deliveryPincode" character varying(6) NOT NULL, "weightGrams" integer NOT NULL DEFAULT '500', "labelUrl" character varying(1000), "trackingUrl" character varying(1000), "orderItemIds" jsonb NOT NULL DEFAULT '[]', "trackingEvents" jsonb NOT NULL DEFAULT '[]', CONSTRAINT "PK_6deda4532ac542a93eab214b564" PRIMARY KEY ("id"))`);
        await queryRunner.query(`CREATE INDEX "IDX_13ba957bcb616719a0dc3fca82" ON "shipments" ("orderId") `);
        await queryRunner.query(`CREATE INDEX "IDX_c28418ad4d761d3951d3b06caf" ON "shipments" ("sellerId") `);
        await queryRunner.query(`CREATE INDEX "IDX_37c938629087411f747f045b80" ON "shipments" ("awbCode") `);
        await queryRunner.query(`CREATE INDEX "IDX_6a19baf6dd62cac42fbb40a518" ON "shipments" ("status") `);
        await queryRunner.query(`CREATE INDEX "IDX_1fff443e2c061101452976c5d1" ON "shipments" ("orderId", "sellerId") `);
        await queryRunner.query(`ALTER TABLE "shipments" ADD CONSTRAINT "FK_13ba957bcb616719a0dc3fca82f" FOREIGN KEY ("orderId") REFERENCES "orders"("id") ON DELETE CASCADE ON UPDATE NO ACTION`);
    }

    public async down(queryRunner: QueryRunner): Promise<void> {
        await queryRunner.query(`ALTER TABLE "shipments" DROP CONSTRAINT "FK_13ba957bcb616719a0dc3fca82f"`);
        await queryRunner.query(`DROP INDEX "public"."IDX_1fff443e2c061101452976c5d1"`);
        await queryRunner.query(`DROP INDEX "public"."IDX_6a19baf6dd62cac42fbb40a518"`);
        await queryRunner.query(`DROP INDEX "public"."IDX_37c938629087411f747f045b80"`);
        await queryRunner.query(`DROP INDEX "public"."IDX_c28418ad4d761d3951d3b06caf"`);
        await queryRunner.query(`DROP INDEX "public"."IDX_13ba957bcb616719a0dc3fca82"`);
        await queryRunner.query(`DROP TABLE "shipments"`);
        await queryRunner.query(`DROP TYPE "public"."shipments_status_enum"`);
    }

}
