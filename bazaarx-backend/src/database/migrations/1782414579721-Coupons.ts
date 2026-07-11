import { MigrationInterface, QueryRunner } from "typeorm";

export class Coupons1782414579721 implements MigrationInterface {
    name = 'Coupons1782414579721'

    public async up(queryRunner: QueryRunner): Promise<void> {
        await queryRunner.query(`CREATE TYPE "public"."coupons_discounttype_enum" AS ENUM('percentage', 'flat')`);
        await queryRunner.query(`CREATE TYPE "public"."coupons_scope_enum" AS ENUM('all', 'category', 'seller')`);
        await queryRunner.query(`CREATE TABLE "coupons" ("id" uuid NOT NULL DEFAULT uuid_generate_v4(), "createdAt" TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT now(), "updatedAt" TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT now(), "deletedAt" TIMESTAMP WITH TIME ZONE, "code" character varying(40) NOT NULL, "description" character varying(200), "discountType" "public"."coupons_discounttype_enum" NOT NULL, "discountValue" integer NOT NULL, "maxDiscountAmount" integer, "minCartValue" integer NOT NULL DEFAULT '0', "scope" "public"."coupons_scope_enum" NOT NULL DEFAULT 'all', "scopeId" uuid, "usageLimit" integer, "perUserLimit" integer NOT NULL DEFAULT '1', "usedCount" integer NOT NULL DEFAULT '0', "validFrom" TIMESTAMP WITH TIME ZONE NOT NULL, "validUntil" TIMESTAMP WITH TIME ZONE NOT NULL, "isActive" boolean NOT NULL DEFAULT true, "createdBySeller" uuid, CONSTRAINT "UQ_e025109230e82925843f2a14c48" UNIQUE ("code"), CONSTRAINT "PK_d7ea8864a0150183770f3e9a8cb" PRIMARY KEY ("id"))`);
        await queryRunner.query(`CREATE UNIQUE INDEX "IDX_e025109230e82925843f2a14c4" ON "coupons" ("code") `);
        await queryRunner.query(`CREATE INDEX "IDX_3650fd30e88e27baa3a88e1e9f" ON "coupons" ("isActive") `);
        await queryRunner.query(`CREATE TABLE "coupon_redemptions" ("id" uuid NOT NULL DEFAULT uuid_generate_v4(), "createdAt" TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT now(), "updatedAt" TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT now(), "deletedAt" TIMESTAMP WITH TIME ZONE, "couponId" uuid NOT NULL, "userId" uuid NOT NULL, "orderId" uuid NOT NULL, "discountAmount" integer NOT NULL, CONSTRAINT "PK_5086813ea980d21dbeb190ed0a7" PRIMARY KEY ("id"))`);
        await queryRunner.query(`CREATE INDEX "IDX_21b5ef20634735e39029e178e7" ON "coupon_redemptions" ("userId") `);
        await queryRunner.query(`CREATE INDEX "IDX_eb006863ca6bbcdeb8ec948ee8" ON "coupon_redemptions" ("orderId") `);
        await queryRunner.query(`CREATE INDEX "IDX_5dc1ed1db4e367f0257ddaca3a" ON "coupon_redemptions" ("couponId", "userId") `);
        await queryRunner.query(`ALTER TABLE "coupon_redemptions" ADD CONSTRAINT "FK_26b8ad24ace2974b2b6c2047d3a" FOREIGN KEY ("couponId") REFERENCES "coupons"("id") ON DELETE CASCADE ON UPDATE NO ACTION`);
    }

    public async down(queryRunner: QueryRunner): Promise<void> {
        await queryRunner.query(`ALTER TABLE "coupon_redemptions" DROP CONSTRAINT "FK_26b8ad24ace2974b2b6c2047d3a"`);
        await queryRunner.query(`DROP INDEX "public"."IDX_5dc1ed1db4e367f0257ddaca3a"`);
        await queryRunner.query(`DROP INDEX "public"."IDX_eb006863ca6bbcdeb8ec948ee8"`);
        await queryRunner.query(`DROP INDEX "public"."IDX_21b5ef20634735e39029e178e7"`);
        await queryRunner.query(`DROP TABLE "coupon_redemptions"`);
        await queryRunner.query(`DROP INDEX "public"."IDX_3650fd30e88e27baa3a88e1e9f"`);
        await queryRunner.query(`DROP INDEX "public"."IDX_e025109230e82925843f2a14c4"`);
        await queryRunner.query(`DROP TABLE "coupons"`);
        await queryRunner.query(`DROP TYPE "public"."coupons_scope_enum"`);
        await queryRunner.query(`DROP TYPE "public"."coupons_discounttype_enum"`);
    }

}
