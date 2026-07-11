import { MigrationInterface, QueryRunner } from "typeorm";

export class Invoices1782380076203 implements MigrationInterface {
    name = 'Invoices1782380076203'

    public async up(queryRunner: QueryRunner): Promise<void> {
        await queryRunner.query(`CREATE TABLE "invoices" ("id" uuid NOT NULL DEFAULT uuid_generate_v4(), "createdAt" TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT now(), "updatedAt" TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT now(), "deletedAt" TIMESTAMP WITH TIME ZONE, "invoiceNumber" character varying(40) NOT NULL, "orderId" uuid NOT NULL, "sellerId" uuid NOT NULL, "data" jsonb NOT NULL, "isIntraState" boolean NOT NULL DEFAULT false, "taxableValue" integer NOT NULL, "totalTax" integer NOT NULL, "grandTotal" integer NOT NULL, "issuedAt" TIMESTAMP WITH TIME ZONE NOT NULL, CONSTRAINT "UQ_bf8e0f9dd4558ef209ec111782d" UNIQUE ("invoiceNumber"), CONSTRAINT "PK_668cef7c22a427fd822cc1be3ce" PRIMARY KEY ("id"))`);
        await queryRunner.query(`CREATE UNIQUE INDEX "IDX_bf8e0f9dd4558ef209ec111782" ON "invoices" ("invoiceNumber") `);
        await queryRunner.query(`CREATE INDEX "IDX_a58a78a0e0031dd93a2f56f1e8" ON "invoices" ("orderId") `);
        await queryRunner.query(`CREATE INDEX "IDX_0b7320e7be48e88e0f408e535d" ON "invoices" ("sellerId") `);
        await queryRunner.query(`CREATE UNIQUE INDEX "IDX_70381d201349b31e6e3c967a56" ON "invoices" ("orderId", "sellerId") `);
        await queryRunner.query(`ALTER TABLE "order_items" ADD "hsnCode" character varying(8) NOT NULL DEFAULT '9999'`);
        await queryRunner.query(`ALTER TABLE "products" ADD "hsnCode" character varying(8) NOT NULL DEFAULT '9999'`);
        await queryRunner.query(`ALTER TABLE "invoices" ADD CONSTRAINT "FK_a58a78a0e0031dd93a2f56f1e8e" FOREIGN KEY ("orderId") REFERENCES "orders"("id") ON DELETE CASCADE ON UPDATE NO ACTION`);
    }

    public async down(queryRunner: QueryRunner): Promise<void> {
        await queryRunner.query(`ALTER TABLE "invoices" DROP CONSTRAINT "FK_a58a78a0e0031dd93a2f56f1e8e"`);
        await queryRunner.query(`ALTER TABLE "products" DROP COLUMN "hsnCode"`);
        await queryRunner.query(`ALTER TABLE "order_items" DROP COLUMN "hsnCode"`);
        await queryRunner.query(`DROP INDEX "public"."IDX_70381d201349b31e6e3c967a56"`);
        await queryRunner.query(`DROP INDEX "public"."IDX_0b7320e7be48e88e0f408e535d"`);
        await queryRunner.query(`DROP INDEX "public"."IDX_a58a78a0e0031dd93a2f56f1e8"`);
        await queryRunner.query(`DROP INDEX "public"."IDX_bf8e0f9dd4558ef209ec111782"`);
        await queryRunner.query(`DROP TABLE "invoices"`);
    }

}
