import { MigrationInterface, QueryRunner } from "typeorm";

export class ProfileAndAddresses1782328619673 implements MigrationInterface {
    name = 'ProfileAndAddresses1782328619673'

    public async up(queryRunner: QueryRunner): Promise<void> {
        await queryRunner.query(`CREATE TYPE "public"."addresses_label_enum" AS ENUM('home', 'work', 'other')`);
        await queryRunner.query(`CREATE TABLE "addresses" ("id" uuid NOT NULL DEFAULT uuid_generate_v4(), "createdAt" TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT now(), "updatedAt" TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT now(), "deletedAt" TIMESTAMP WITH TIME ZONE, "userId" uuid NOT NULL, "label" "public"."addresses_label_enum" NOT NULL DEFAULT 'home', "name" character varying(100) NOT NULL, "mobile" character varying(10) NOT NULL, "line1" character varying(255) NOT NULL, "line2" character varying(255), "city" character varying(100) NOT NULL, "state" character varying(100) NOT NULL, "pincode" character varying(6) NOT NULL, "landmark" character varying(255), "latitude" numeric(10,7), "longitude" numeric(10,7), "isDefault" boolean NOT NULL DEFAULT false, CONSTRAINT "PK_745d8f43d3af10ab8247465e450" PRIMARY KEY ("id"))`);
        await queryRunner.query(`CREATE INDEX "IDX_95c93a584de49f0b0e13f75363" ON "addresses" ("userId") `);
        await queryRunner.query(`CREATE INDEX "IDX_269f681f91d0eb6e104af6748e" ON "addresses" ("pincode") `);
        await queryRunner.query(`ALTER TABLE "users" ADD "dateOfBirth" date`);
        await queryRunner.query(`CREATE TYPE "public"."users_gender_enum" AS ENUM('male', 'female', 'other', 'prefer_not_to_say')`);
        await queryRunner.query(`ALTER TABLE "users" ADD "gender" "public"."users_gender_enum"`);
        await queryRunner.query(`ALTER TABLE "users" ADD "avatarUrl" character varying(500)`);
        await queryRunner.query(`CREATE TYPE "public"."users_preferredlanguage_enum" AS ENUM('en', 'hi', 'ta', 'te', 'bn', 'mr', 'kn', 'gu', 'ml')`);
        await queryRunner.query(`ALTER TABLE "users" ADD "preferredLanguage" "public"."users_preferredlanguage_enum" NOT NULL DEFAULT 'en'`);
        await queryRunner.query(`ALTER TABLE "addresses" ADD CONSTRAINT "FK_95c93a584de49f0b0e13f753630" FOREIGN KEY ("userId") REFERENCES "users"("id") ON DELETE CASCADE ON UPDATE NO ACTION`);
    }

    public async down(queryRunner: QueryRunner): Promise<void> {
        await queryRunner.query(`ALTER TABLE "addresses" DROP CONSTRAINT "FK_95c93a584de49f0b0e13f753630"`);
        await queryRunner.query(`ALTER TABLE "users" DROP COLUMN "preferredLanguage"`);
        await queryRunner.query(`DROP TYPE "public"."users_preferredlanguage_enum"`);
        await queryRunner.query(`ALTER TABLE "users" DROP COLUMN "avatarUrl"`);
        await queryRunner.query(`ALTER TABLE "users" DROP COLUMN "gender"`);
        await queryRunner.query(`DROP TYPE "public"."users_gender_enum"`);
        await queryRunner.query(`ALTER TABLE "users" DROP COLUMN "dateOfBirth"`);
        await queryRunner.query(`DROP INDEX "public"."IDX_269f681f91d0eb6e104af6748e"`);
        await queryRunner.query(`DROP INDEX "public"."IDX_95c93a584de49f0b0e13f75363"`);
        await queryRunner.query(`DROP TABLE "addresses"`);
        await queryRunner.query(`DROP TYPE "public"."addresses_label_enum"`);
    }

}
