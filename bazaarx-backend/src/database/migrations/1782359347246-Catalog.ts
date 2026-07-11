import { MigrationInterface, QueryRunner } from "typeorm";

export class Catalog1782359347246 implements MigrationInterface {
    name = 'Catalog1782359347246'

    public async up(queryRunner: QueryRunner): Promise<void> {
        await queryRunner.query(`CREATE TABLE "categories" ("id" uuid NOT NULL DEFAULT uuid_generate_v4(), "createdAt" TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT now(), "updatedAt" TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT now(), "deletedAt" TIMESTAMP WITH TIME ZONE, "name" character varying(150) NOT NULL, "slug" character varying(180) NOT NULL, "parentId" uuid, "level" smallint NOT NULL DEFAULT '0', "imageUrl" character varying(500), "iconUrl" character varying(500), "isActive" boolean NOT NULL DEFAULT true, "sortOrder" integer NOT NULL DEFAULT '0', "commissionRate" numeric(5,2) NOT NULL DEFAULT '5', "gstRate" numeric(5,2) NOT NULL DEFAULT '18', "metaTitle" character varying(255), "metaDescription" character varying(500), CONSTRAINT "UQ_420d9f679d41281f282f5bc7d09" UNIQUE ("slug"), CONSTRAINT "PK_24dbc6126a28ff948da33e97d3b" PRIMARY KEY ("id"))`);
        await queryRunner.query(`CREATE UNIQUE INDEX "IDX_420d9f679d41281f282f5bc7d0" ON "categories" ("slug") `);
        await queryRunner.query(`CREATE INDEX "IDX_9a6f051e66982b5f0318981bca" ON "categories" ("parentId") `);
        await queryRunner.query(`CREATE INDEX "IDX_77d4cad977bd471fb670059561" ON "categories" ("isActive") `);
        await queryRunner.query(`CREATE TABLE "brands" ("id" uuid NOT NULL DEFAULT uuid_generate_v4(), "createdAt" TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT now(), "updatedAt" TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT now(), "deletedAt" TIMESTAMP WITH TIME ZONE, "name" character varying(150) NOT NULL, "slug" character varying(180) NOT NULL, "logoUrl" character varying(500), "description" text, "isActive" boolean NOT NULL DEFAULT true, CONSTRAINT "UQ_b15428f362be2200922952dc268" UNIQUE ("slug"), CONSTRAINT "PK_b0c437120b624da1034a81fc561" PRIMARY KEY ("id"))`);
        await queryRunner.query(`CREATE UNIQUE INDEX "IDX_b15428f362be2200922952dc26" ON "brands" ("slug") `);
        await queryRunner.query(`CREATE INDEX "IDX_36c435d1f3724d54947873161f" ON "brands" ("isActive") `);
        await queryRunner.query(`CREATE TABLE "product_variants" ("id" uuid NOT NULL DEFAULT uuid_generate_v4(), "createdAt" TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT now(), "updatedAt" TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT now(), "deletedAt" TIMESTAMP WITH TIME ZONE, "productId" uuid NOT NULL, "sku" character varying(100) NOT NULL, "attributes" jsonb NOT NULL DEFAULT '{}', "mrp" integer NOT NULL, "sellingPrice" integer NOT NULL, "stockQuantity" integer NOT NULL DEFAULT '0', "lowStockThreshold" integer NOT NULL DEFAULT '5', "imageUrls" jsonb NOT NULL DEFAULT '[]', "weightGrams" integer, "isActive" boolean NOT NULL DEFAULT true, CONSTRAINT "UQ_46f236f21640f9da218a063a866" UNIQUE ("sku"), CONSTRAINT "PK_281e3f2c55652d6a22c0aa59fd7" PRIMARY KEY ("id"))`);
        await queryRunner.query(`CREATE INDEX "IDX_f515690c571a03400a9876600b" ON "product_variants" ("productId") `);
        await queryRunner.query(`CREATE UNIQUE INDEX "IDX_46f236f21640f9da218a063a86" ON "product_variants" ("sku") `);
        await queryRunner.query(`CREATE INDEX "IDX_74f84d49e67995a1e46c402eab" ON "product_variants" ("isActive") `);
        await queryRunner.query(`CREATE TYPE "public"."products_status_enum" AS ENUM('draft', 'pending_review', 'active', 'rejected', 'inactive')`);
        await queryRunner.query(`CREATE TABLE "products" ("id" uuid NOT NULL DEFAULT uuid_generate_v4(), "createdAt" TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT now(), "updatedAt" TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT now(), "deletedAt" TIMESTAMP WITH TIME ZONE, "sellerId" uuid NOT NULL, "categoryId" uuid NOT NULL, "brandId" uuid, "title" character varying(300) NOT NULL, "slug" character varying(350) NOT NULL, "description" text, "highlights" jsonb NOT NULL DEFAULT '[]', "specifications" jsonb NOT NULL DEFAULT '{}', "tags" jsonb NOT NULL DEFAULT '[]', "status" "public"."products_status_enum" NOT NULL DEFAULT 'draft', "rejectionReason" character varying(500), "avgRating" numeric(3,2) NOT NULL DEFAULT '0', "reviewCount" integer NOT NULL DEFAULT '0', "metaTitle" character varying(255), "metaDescription" character varying(500), CONSTRAINT "UQ_464f927ae360106b783ed0b4106" UNIQUE ("slug"), CONSTRAINT "PK_0806c755e0aca124e67c0cf6d7d" PRIMARY KEY ("id"))`);
        await queryRunner.query(`CREATE INDEX "IDX_e40a1dd2909378f0da1f34f7bd" ON "products" ("sellerId") `);
        await queryRunner.query(`CREATE INDEX "IDX_ff56834e735fa78a15d0cf2192" ON "products" ("categoryId") `);
        await queryRunner.query(`CREATE INDEX "IDX_ea86d0c514c4ecbb5694cbf57d" ON "products" ("brandId") `);
        await queryRunner.query(`CREATE UNIQUE INDEX "IDX_464f927ae360106b783ed0b410" ON "products" ("slug") `);
        await queryRunner.query(`CREATE INDEX "IDX_1846199852a695713b1f8f5e9a" ON "products" ("status") `);
        await queryRunner.query(`CREATE INDEX "IDX_f204e865324cb7ee35238d077d" ON "products" ("status", "categoryId") `);
        await queryRunner.query(`ALTER TABLE "categories" ADD CONSTRAINT "FK_9a6f051e66982b5f0318981bcaa" FOREIGN KEY ("parentId") REFERENCES "categories"("id") ON DELETE CASCADE ON UPDATE NO ACTION`);
        await queryRunner.query(`ALTER TABLE "product_variants" ADD CONSTRAINT "FK_f515690c571a03400a9876600b5" FOREIGN KEY ("productId") REFERENCES "products"("id") ON DELETE CASCADE ON UPDATE NO ACTION`);
        await queryRunner.query(`ALTER TABLE "products" ADD CONSTRAINT "FK_e40a1dd2909378f0da1f34f7bd6" FOREIGN KEY ("sellerId") REFERENCES "users"("id") ON DELETE CASCADE ON UPDATE NO ACTION`);
        await queryRunner.query(`ALTER TABLE "products" ADD CONSTRAINT "FK_ff56834e735fa78a15d0cf21926" FOREIGN KEY ("categoryId") REFERENCES "categories"("id") ON DELETE RESTRICT ON UPDATE NO ACTION`);
        await queryRunner.query(`ALTER TABLE "products" ADD CONSTRAINT "FK_ea86d0c514c4ecbb5694cbf57df" FOREIGN KEY ("brandId") REFERENCES "brands"("id") ON DELETE SET NULL ON UPDATE NO ACTION`);
    }

    public async down(queryRunner: QueryRunner): Promise<void> {
        await queryRunner.query(`ALTER TABLE "products" DROP CONSTRAINT "FK_ea86d0c514c4ecbb5694cbf57df"`);
        await queryRunner.query(`ALTER TABLE "products" DROP CONSTRAINT "FK_ff56834e735fa78a15d0cf21926"`);
        await queryRunner.query(`ALTER TABLE "products" DROP CONSTRAINT "FK_e40a1dd2909378f0da1f34f7bd6"`);
        await queryRunner.query(`ALTER TABLE "product_variants" DROP CONSTRAINT "FK_f515690c571a03400a9876600b5"`);
        await queryRunner.query(`ALTER TABLE "categories" DROP CONSTRAINT "FK_9a6f051e66982b5f0318981bcaa"`);
        await queryRunner.query(`DROP INDEX "public"."IDX_f204e865324cb7ee35238d077d"`);
        await queryRunner.query(`DROP INDEX "public"."IDX_1846199852a695713b1f8f5e9a"`);
        await queryRunner.query(`DROP INDEX "public"."IDX_464f927ae360106b783ed0b410"`);
        await queryRunner.query(`DROP INDEX "public"."IDX_ea86d0c514c4ecbb5694cbf57d"`);
        await queryRunner.query(`DROP INDEX "public"."IDX_ff56834e735fa78a15d0cf2192"`);
        await queryRunner.query(`DROP INDEX "public"."IDX_e40a1dd2909378f0da1f34f7bd"`);
        await queryRunner.query(`DROP TABLE "products"`);
        await queryRunner.query(`DROP TYPE "public"."products_status_enum"`);
        await queryRunner.query(`DROP INDEX "public"."IDX_74f84d49e67995a1e46c402eab"`);
        await queryRunner.query(`DROP INDEX "public"."IDX_46f236f21640f9da218a063a86"`);
        await queryRunner.query(`DROP INDEX "public"."IDX_f515690c571a03400a9876600b"`);
        await queryRunner.query(`DROP TABLE "product_variants"`);
        await queryRunner.query(`DROP INDEX "public"."IDX_36c435d1f3724d54947873161f"`);
        await queryRunner.query(`DROP INDEX "public"."IDX_b15428f362be2200922952dc26"`);
        await queryRunner.query(`DROP TABLE "brands"`);
        await queryRunner.query(`DROP INDEX "public"."IDX_77d4cad977bd471fb670059561"`);
        await queryRunner.query(`DROP INDEX "public"."IDX_9a6f051e66982b5f0318981bca"`);
        await queryRunner.query(`DROP INDEX "public"."IDX_420d9f679d41281f282f5bc7d0"`);
        await queryRunner.query(`DROP TABLE "categories"`);
    }

}
