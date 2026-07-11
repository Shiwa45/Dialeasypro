import { MigrationInterface, QueryRunner } from "typeorm";

export class InitUsers1782328162840 implements MigrationInterface {
    name = 'InitUsers1782328162840'

    public async up(queryRunner: QueryRunner): Promise<void> {
        await queryRunner.query(`CREATE TYPE "public"."users_role_enum" AS ENUM('buyer', 'seller', 'admin')`);
        await queryRunner.query(`CREATE TABLE "users" ("id" uuid NOT NULL DEFAULT uuid_generate_v4(), "createdAt" TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT now(), "updatedAt" TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT now(), "deletedAt" TIMESTAMP WITH TIME ZONE, "mobile" character varying(10) NOT NULL, "email" character varying(255), "passwordHash" character varying(255), "firstName" character varying(100), "lastName" character varying(100), "role" "public"."users_role_enum" NOT NULL DEFAULT 'buyer', "isMobileVerified" boolean NOT NULL DEFAULT false, "isEmailVerified" boolean NOT NULL DEFAULT false, "isActive" boolean NOT NULL DEFAULT true, "lastLoginAt" TIMESTAMP WITH TIME ZONE, CONSTRAINT "UQ_d376a9f93bba651f32a2c03a7d3" UNIQUE ("mobile"), CONSTRAINT "PK_a3ffb1c0c8416b9fc6f907b7433" PRIMARY KEY ("id"))`);
        await queryRunner.query(`CREATE UNIQUE INDEX "IDX_d376a9f93bba651f32a2c03a7d" ON "users" ("mobile") `);
        await queryRunner.query(`CREATE UNIQUE INDEX "IDX_65cbf5fcb331619593ee334c7c" ON "users" ("email") WHERE email IS NOT NULL`);
    }

    public async down(queryRunner: QueryRunner): Promise<void> {
        await queryRunner.query(`DROP INDEX "public"."IDX_65cbf5fcb331619593ee334c7c"`);
        await queryRunner.query(`DROP INDEX "public"."IDX_d376a9f93bba651f32a2c03a7d"`);
        await queryRunner.query(`DROP TABLE "users"`);
        await queryRunner.query(`DROP TYPE "public"."users_role_enum"`);
    }

}
