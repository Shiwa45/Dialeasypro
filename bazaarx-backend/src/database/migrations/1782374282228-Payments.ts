import { MigrationInterface, QueryRunner } from "typeorm";

export class Payments1782374282228 implements MigrationInterface {
    name = 'Payments1782374282228'

    public async up(queryRunner: QueryRunner): Promise<void> {
        await queryRunner.query(`CREATE TYPE "public"."payments_gateway_enum" AS ENUM('razorpay')`);
        await queryRunner.query(`CREATE TYPE "public"."payments_status_enum" AS ENUM('created', 'captured', 'failed', 'refunded')`);
        await queryRunner.query(`CREATE TABLE "payments" ("id" uuid NOT NULL DEFAULT uuid_generate_v4(), "createdAt" TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT now(), "updatedAt" TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT now(), "deletedAt" TIMESTAMP WITH TIME ZONE, "orderId" uuid NOT NULL, "gateway" "public"."payments_gateway_enum" NOT NULL DEFAULT 'razorpay', "gatewayOrderId" character varying(100) NOT NULL, "gatewayPaymentId" character varying(100), "amount" integer NOT NULL, "currency" character varying(3) NOT NULL DEFAULT 'INR', "status" "public"."payments_status_enum" NOT NULL DEFAULT 'created', "method" character varying(50), "errorCode" character varying(100), "errorDescription" character varying(500), CONSTRAINT "PK_197ab7af18c93fbb0c9b28b4a59" PRIMARY KEY ("id"))`);
        await queryRunner.query(`CREATE INDEX "IDX_af929a5f2a400fdb6913b4967e" ON "payments" ("orderId") `);
        await queryRunner.query(`CREATE UNIQUE INDEX "IDX_cd19dcf01dffc25c7a84acbb40" ON "payments" ("gatewayOrderId") `);
        await queryRunner.query(`CREATE INDEX "IDX_32b41cdb985a296213e9a928b5" ON "payments" ("status") `);
        await queryRunner.query(`ALTER TYPE "public"."order_items_status_enum" RENAME TO "order_items_status_enum_old"`);
        await queryRunner.query(`CREATE TYPE "public"."order_items_status_enum" AS ENUM('pending_payment', 'placed', 'confirmed', 'packed', 'shipped', 'out_for_delivery', 'delivered', 'cancelled', 'returned')`);
        await queryRunner.query(`ALTER TABLE "order_items" ALTER COLUMN "status" DROP DEFAULT`);
        await queryRunner.query(`ALTER TABLE "order_items" ALTER COLUMN "status" TYPE "public"."order_items_status_enum" USING "status"::"text"::"public"."order_items_status_enum"`);
        await queryRunner.query(`ALTER TABLE "order_items" ALTER COLUMN "status" SET DEFAULT 'placed'`);
        await queryRunner.query(`DROP TYPE "public"."order_items_status_enum_old"`);
        await queryRunner.query(`ALTER TABLE "payments" ADD CONSTRAINT "FK_af929a5f2a400fdb6913b4967e1" FOREIGN KEY ("orderId") REFERENCES "orders"("id") ON DELETE CASCADE ON UPDATE NO ACTION`);
    }

    public async down(queryRunner: QueryRunner): Promise<void> {
        await queryRunner.query(`ALTER TABLE "payments" DROP CONSTRAINT "FK_af929a5f2a400fdb6913b4967e1"`);
        await queryRunner.query(`CREATE TYPE "public"."order_items_status_enum_old" AS ENUM('placed', 'confirmed', 'packed', 'shipped', 'out_for_delivery', 'delivered', 'cancelled', 'returned')`);
        await queryRunner.query(`ALTER TABLE "order_items" ALTER COLUMN "status" DROP DEFAULT`);
        await queryRunner.query(`ALTER TABLE "order_items" ALTER COLUMN "status" TYPE "public"."order_items_status_enum_old" USING "status"::"text"::"public"."order_items_status_enum_old"`);
        await queryRunner.query(`ALTER TABLE "order_items" ALTER COLUMN "status" SET DEFAULT 'placed'`);
        await queryRunner.query(`DROP TYPE "public"."order_items_status_enum"`);
        await queryRunner.query(`ALTER TYPE "public"."order_items_status_enum_old" RENAME TO "order_items_status_enum"`);
        await queryRunner.query(`DROP INDEX "public"."IDX_32b41cdb985a296213e9a928b5"`);
        await queryRunner.query(`DROP INDEX "public"."IDX_cd19dcf01dffc25c7a84acbb40"`);
        await queryRunner.query(`DROP INDEX "public"."IDX_af929a5f2a400fdb6913b4967e"`);
        await queryRunner.query(`DROP TABLE "payments"`);
        await queryRunner.query(`DROP TYPE "public"."payments_status_enum"`);
        await queryRunner.query(`DROP TYPE "public"."payments_gateway_enum"`);
    }

}
