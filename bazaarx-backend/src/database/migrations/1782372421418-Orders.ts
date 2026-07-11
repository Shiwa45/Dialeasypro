import { MigrationInterface, QueryRunner } from "typeorm";

export class Orders1782372421418 implements MigrationInterface {
    name = 'Orders1782372421418'

    public async up(queryRunner: QueryRunner): Promise<void> {
        await queryRunner.query(`CREATE TYPE "public"."order_items_status_enum" AS ENUM('placed', 'confirmed', 'packed', 'shipped', 'out_for_delivery', 'delivered', 'cancelled', 'returned')`);
        await queryRunner.query(`CREATE TABLE "order_items" ("id" uuid NOT NULL DEFAULT uuid_generate_v4(), "createdAt" TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT now(), "updatedAt" TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT now(), "deletedAt" TIMESTAMP WITH TIME ZONE, "orderId" uuid NOT NULL, "sellerId" uuid NOT NULL, "productId" uuid NOT NULL, "variantId" uuid NOT NULL, "productTitle" character varying(300) NOT NULL, "sku" character varying(100) NOT NULL, "attributes" jsonb NOT NULL DEFAULT '{}', "imageUrl" character varying(1000), "unitPrice" integer NOT NULL, "quantity" integer NOT NULL, "gstRate" numeric(5,2) NOT NULL, "gstAmount" integer NOT NULL, "lineTotal" integer NOT NULL, "status" "public"."order_items_status_enum" NOT NULL DEFAULT 'placed', "awbNumber" character varying(100), "cancelReason" character varying(500), CONSTRAINT "PK_005269d8574e6fac0493715c308" PRIMARY KEY ("id"))`);
        await queryRunner.query(`CREATE INDEX "IDX_f1d359a55923bb45b057fbdab0" ON "order_items" ("orderId") `);
        await queryRunner.query(`CREATE INDEX "IDX_1200397d761353a3a79f593b9e" ON "order_items" ("sellerId") `);
        await queryRunner.query(`CREATE INDEX "IDX_f421c8981cca05954f98667134" ON "order_items" ("status") `);
        await queryRunner.query(`CREATE TYPE "public"."orders_paymentmethod_enum" AS ENUM('cod', 'upi', 'card', 'netbanking', 'wallet')`);
        await queryRunner.query(`CREATE TYPE "public"."orders_paymentstatus_enum" AS ENUM('pending', 'paid', 'failed', 'refunded')`);
        await queryRunner.query(`CREATE TABLE "orders" ("id" uuid NOT NULL DEFAULT uuid_generate_v4(), "createdAt" TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT now(), "updatedAt" TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT now(), "deletedAt" TIMESTAMP WITH TIME ZONE, "orderNumber" character varying(30) NOT NULL, "userId" uuid NOT NULL, "shippingAddress" jsonb NOT NULL, "paymentMethod" "public"."orders_paymentmethod_enum" NOT NULL, "paymentStatus" "public"."orders_paymentstatus_enum" NOT NULL DEFAULT 'pending', "itemsSubtotal" integer NOT NULL, "gstAmount" integer NOT NULL DEFAULT '0', "deliveryCharge" integer NOT NULL DEFAULT '0', "discountAmount" integer NOT NULL DEFAULT '0', "totalAmount" integer NOT NULL, "placedAt" TIMESTAMP WITH TIME ZONE NOT NULL, CONSTRAINT "UQ_59b0c3b34ea0fa5562342f24143" UNIQUE ("orderNumber"), CONSTRAINT "PK_710e2d4957aa5878dfe94e4ac2f" PRIMARY KEY ("id"))`);
        await queryRunner.query(`CREATE UNIQUE INDEX "IDX_59b0c3b34ea0fa5562342f2414" ON "orders" ("orderNumber") `);
        await queryRunner.query(`CREATE INDEX "IDX_151b79a83ba240b0cb31b2302d" ON "orders" ("userId") `);
        await queryRunner.query(`CREATE INDEX "IDX_01b20118a3f640214e7a8a6b29" ON "orders" ("paymentStatus") `);
        await queryRunner.query(`ALTER TABLE "order_items" ADD CONSTRAINT "FK_f1d359a55923bb45b057fbdab0d" FOREIGN KEY ("orderId") REFERENCES "orders"("id") ON DELETE CASCADE ON UPDATE NO ACTION`);
        await queryRunner.query(`ALTER TABLE "orders" ADD CONSTRAINT "FK_151b79a83ba240b0cb31b2302d1" FOREIGN KEY ("userId") REFERENCES "users"("id") ON DELETE RESTRICT ON UPDATE NO ACTION`);
    }

    public async down(queryRunner: QueryRunner): Promise<void> {
        await queryRunner.query(`ALTER TABLE "orders" DROP CONSTRAINT "FK_151b79a83ba240b0cb31b2302d1"`);
        await queryRunner.query(`ALTER TABLE "order_items" DROP CONSTRAINT "FK_f1d359a55923bb45b057fbdab0d"`);
        await queryRunner.query(`DROP INDEX "public"."IDX_01b20118a3f640214e7a8a6b29"`);
        await queryRunner.query(`DROP INDEX "public"."IDX_151b79a83ba240b0cb31b2302d"`);
        await queryRunner.query(`DROP INDEX "public"."IDX_59b0c3b34ea0fa5562342f2414"`);
        await queryRunner.query(`DROP TABLE "orders"`);
        await queryRunner.query(`DROP TYPE "public"."orders_paymentstatus_enum"`);
        await queryRunner.query(`DROP TYPE "public"."orders_paymentmethod_enum"`);
        await queryRunner.query(`DROP INDEX "public"."IDX_f421c8981cca05954f98667134"`);
        await queryRunner.query(`DROP INDEX "public"."IDX_1200397d761353a3a79f593b9e"`);
        await queryRunner.query(`DROP INDEX "public"."IDX_f1d359a55923bb45b057fbdab0"`);
        await queryRunner.query(`DROP TABLE "order_items"`);
        await queryRunner.query(`DROP TYPE "public"."order_items_status_enum"`);
    }

}
