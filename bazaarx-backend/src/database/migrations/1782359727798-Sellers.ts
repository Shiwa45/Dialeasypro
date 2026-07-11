import { MigrationInterface, QueryRunner } from "typeorm";

export class Sellers1782359727798 implements MigrationInterface {
    name = 'Sellers1782359727798'

    public async up(queryRunner: QueryRunner): Promise<void> {
        await queryRunner.query(`CREATE TYPE "public"."seller_documents_type_enum" AS ENUM('gst_certificate', 'pan_card', 'aadhaar', 'bank_proof', 'fssai')`);
        await queryRunner.query(`CREATE TYPE "public"."seller_documents_status_enum" AS ENUM('pending', 'verified', 'rejected')`);
        await queryRunner.query(`CREATE TABLE "seller_documents" ("id" uuid NOT NULL DEFAULT uuid_generate_v4(), "createdAt" TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT now(), "updatedAt" TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT now(), "deletedAt" TIMESTAMP WITH TIME ZONE, "sellerId" uuid NOT NULL, "type" "public"."seller_documents_type_enum" NOT NULL, "fileUrl" character varying(1000) NOT NULL, "status" "public"."seller_documents_status_enum" NOT NULL DEFAULT 'pending', "rejectionReason" character varying(500), CONSTRAINT "PK_21b439eb3e12ca544b8031c8423" PRIMARY KEY ("id"))`);
        await queryRunner.query(`CREATE INDEX "IDX_7b6226f49a7dae7ff1b7a607b5" ON "seller_documents" ("sellerId") `);
        await queryRunner.query(`CREATE TYPE "public"."sellers_businesstype_enum" AS ENUM('individual', 'proprietorship', 'partnership', 'llp', 'private_limited')`);
        await queryRunner.query(`CREATE TYPE "public"."sellers_status_enum" AS ENUM('pending', 'approved', 'rejected', 'suspended')`);
        await queryRunner.query(`CREATE TABLE "sellers" ("id" uuid NOT NULL DEFAULT uuid_generate_v4(), "createdAt" TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT now(), "updatedAt" TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT now(), "deletedAt" TIMESTAMP WITH TIME ZONE, "userId" uuid NOT NULL, "displayName" character varying(200) NOT NULL, "businessName" character varying(200) NOT NULL, "businessType" "public"."sellers_businesstype_enum" NOT NULL, "gstin" character varying(15) NOT NULL, "pan" character varying(10) NOT NULL, "bankAccountHolder" character varying(150) NOT NULL, "bankAccountNumber" character varying(20) NOT NULL, "bankIfsc" character varying(11) NOT NULL, "status" "public"."sellers_status_enum" NOT NULL DEFAULT 'pending', "rejectionReason" character varying(500), "accountHealthScore" numeric(5,2) NOT NULL DEFAULT '100', "commissionOverride" numeric(5,2), "approvedAt" TIMESTAMP WITH TIME ZONE, "approvedByAdminId" uuid, CONSTRAINT "UQ_4c1c59db4ac1ed90a1a7c0ff3df" UNIQUE ("userId"), CONSTRAINT "UQ_8eebbb5121d22f2b0e11b375365" UNIQUE ("gstin"), CONSTRAINT "REL_4c1c59db4ac1ed90a1a7c0ff3d" UNIQUE ("userId"), CONSTRAINT "PK_97337ccbf692c58e6c7682de8a2" PRIMARY KEY ("id"))`);
        await queryRunner.query(`CREATE UNIQUE INDEX "IDX_4c1c59db4ac1ed90a1a7c0ff3d" ON "sellers" ("userId") `);
        await queryRunner.query(`CREATE UNIQUE INDEX "IDX_8eebbb5121d22f2b0e11b37536" ON "sellers" ("gstin") `);
        await queryRunner.query(`CREATE INDEX "IDX_b99cb17a41a10ffa3d4d0481d7" ON "sellers" ("status") `);
        await queryRunner.query(`ALTER TABLE "seller_documents" ADD CONSTRAINT "FK_7b6226f49a7dae7ff1b7a607b53" FOREIGN KEY ("sellerId") REFERENCES "sellers"("id") ON DELETE CASCADE ON UPDATE NO ACTION`);
        await queryRunner.query(`ALTER TABLE "sellers" ADD CONSTRAINT "FK_4c1c59db4ac1ed90a1a7c0ff3df" FOREIGN KEY ("userId") REFERENCES "users"("id") ON DELETE CASCADE ON UPDATE NO ACTION`);
    }

    public async down(queryRunner: QueryRunner): Promise<void> {
        await queryRunner.query(`ALTER TABLE "sellers" DROP CONSTRAINT "FK_4c1c59db4ac1ed90a1a7c0ff3df"`);
        await queryRunner.query(`ALTER TABLE "seller_documents" DROP CONSTRAINT "FK_7b6226f49a7dae7ff1b7a607b53"`);
        await queryRunner.query(`DROP INDEX "public"."IDX_b99cb17a41a10ffa3d4d0481d7"`);
        await queryRunner.query(`DROP INDEX "public"."IDX_8eebbb5121d22f2b0e11b37536"`);
        await queryRunner.query(`DROP INDEX "public"."IDX_4c1c59db4ac1ed90a1a7c0ff3d"`);
        await queryRunner.query(`DROP TABLE "sellers"`);
        await queryRunner.query(`DROP TYPE "public"."sellers_status_enum"`);
        await queryRunner.query(`DROP TYPE "public"."sellers_businesstype_enum"`);
        await queryRunner.query(`DROP INDEX "public"."IDX_7b6226f49a7dae7ff1b7a607b5"`);
        await queryRunner.query(`DROP TABLE "seller_documents"`);
        await queryRunner.query(`DROP TYPE "public"."seller_documents_status_enum"`);
        await queryRunner.query(`DROP TYPE "public"."seller_documents_type_enum"`);
    }

}
