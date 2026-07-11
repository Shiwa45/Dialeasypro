import { MigrationInterface, QueryRunner } from "typeorm";

export class Reviews1782414967899 implements MigrationInterface {
    name = 'Reviews1782414967899'

    public async up(queryRunner: QueryRunner): Promise<void> {
        await queryRunner.query(`CREATE TYPE "public"."reviews_status_enum" AS ENUM('visible', 'hidden')`);
        await queryRunner.query(`CREATE TABLE "reviews" ("id" uuid NOT NULL DEFAULT uuid_generate_v4(), "createdAt" TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT now(), "updatedAt" TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT now(), "deletedAt" TIMESTAMP WITH TIME ZONE, "productId" uuid NOT NULL, "userId" uuid NOT NULL, "orderItemId" uuid, "rating" smallint NOT NULL, "title" character varying(150), "comment" character varying(2000), "images" jsonb NOT NULL DEFAULT '[]', "isVerifiedPurchase" boolean NOT NULL DEFAULT true, "helpfulCount" integer NOT NULL DEFAULT '0', "sellerResponse" character varying(2000), "sellerRespondedAt" TIMESTAMP WITH TIME ZONE, "status" "public"."reviews_status_enum" NOT NULL DEFAULT 'visible', CONSTRAINT "PK_231ae565c273ee700b283f15c1d" PRIMARY KEY ("id"))`);
        await queryRunner.query(`CREATE INDEX "IDX_a6b3c434392f5d10ec17104366" ON "reviews" ("productId") `);
        await queryRunner.query(`CREATE INDEX "IDX_7ed5659e7139fc8bc039198cc1" ON "reviews" ("userId") `);
        await queryRunner.query(`CREATE INDEX "IDX_7b06c23cf52ca8aea0dcaf0ee2" ON "reviews" ("status") `);
        await queryRunner.query(`CREATE UNIQUE INDEX "IDX_9007ffba411fd471dfe233dabf" ON "reviews" ("productId", "userId") `);
        await queryRunner.query(`CREATE TABLE "review_votes" ("id" uuid NOT NULL DEFAULT uuid_generate_v4(), "createdAt" TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT now(), "updatedAt" TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT now(), "deletedAt" TIMESTAMP WITH TIME ZONE, "reviewId" uuid NOT NULL, "userId" uuid NOT NULL, CONSTRAINT "PK_687569add3c5a70950438fa0cee" PRIMARY KEY ("id"))`);
        await queryRunner.query(`CREATE INDEX "IDX_f34aa40b63e1adedf862325404" ON "review_votes" ("userId") `);
        await queryRunner.query(`CREATE UNIQUE INDEX "IDX_dff9fe2e660dfcac9542bc06c1" ON "review_votes" ("reviewId", "userId") `);
        await queryRunner.query(`ALTER TABLE "reviews" ADD CONSTRAINT "FK_a6b3c434392f5d10ec171043666" FOREIGN KEY ("productId") REFERENCES "products"("id") ON DELETE CASCADE ON UPDATE NO ACTION`);
        await queryRunner.query(`ALTER TABLE "review_votes" ADD CONSTRAINT "FK_35fdcea131e84362d9eb6573ce8" FOREIGN KEY ("reviewId") REFERENCES "reviews"("id") ON DELETE CASCADE ON UPDATE NO ACTION`);
    }

    public async down(queryRunner: QueryRunner): Promise<void> {
        await queryRunner.query(`ALTER TABLE "review_votes" DROP CONSTRAINT "FK_35fdcea131e84362d9eb6573ce8"`);
        await queryRunner.query(`ALTER TABLE "reviews" DROP CONSTRAINT "FK_a6b3c434392f5d10ec171043666"`);
        await queryRunner.query(`DROP INDEX "public"."IDX_dff9fe2e660dfcac9542bc06c1"`);
        await queryRunner.query(`DROP INDEX "public"."IDX_f34aa40b63e1adedf862325404"`);
        await queryRunner.query(`DROP TABLE "review_votes"`);
        await queryRunner.query(`DROP INDEX "public"."IDX_9007ffba411fd471dfe233dabf"`);
        await queryRunner.query(`DROP INDEX "public"."IDX_7b06c23cf52ca8aea0dcaf0ee2"`);
        await queryRunner.query(`DROP INDEX "public"."IDX_7ed5659e7139fc8bc039198cc1"`);
        await queryRunner.query(`DROP INDEX "public"."IDX_a6b3c434392f5d10ec17104366"`);
        await queryRunner.query(`DROP TABLE "reviews"`);
        await queryRunner.query(`DROP TYPE "public"."reviews_status_enum"`);
    }

}
