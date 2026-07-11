import { MigrationInterface, QueryRunner } from "typeorm";

export class Returns1782414146466 implements MigrationInterface {
    name = 'Returns1782414146466'

    public async up(queryRunner: QueryRunner): Promise<void> {
        await queryRunner.query(`CREATE TYPE "public"."returns_reason_enum" AS ENUM('damaged', 'defective', 'wrong_item', 'not_as_described', 'size_fit', 'no_longer_needed')`);
        await queryRunner.query(`CREATE TYPE "public"."returns_status_enum" AS ENUM('requested', 'approved', 'rejected', 'picked_up', 'received', 'refunded', 'cancelled')`);
        await queryRunner.query(`CREATE TYPE "public"."returns_refundmethod_enum" AS ENUM('razorpay', 'wallet')`);
        await queryRunner.query(`CREATE TABLE "returns" ("id" uuid NOT NULL DEFAULT uuid_generate_v4(), "createdAt" TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT now(), "updatedAt" TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT now(), "deletedAt" TIMESTAMP WITH TIME ZONE, "returnNumber" character varying(30) NOT NULL, "orderId" uuid NOT NULL, "orderItemId" uuid NOT NULL, "buyerId" uuid NOT NULL, "sellerId" uuid NOT NULL, "reason" "public"."returns_reason_enum" NOT NULL, "comments" character varying(1000), "status" "public"."returns_status_enum" NOT NULL DEFAULT 'requested', "rejectionReason" character varying(500), "reverseAwb" character varying(100), "refundAmount" integer NOT NULL, "refundMethod" "public"."returns_refundmethod_enum", "refundReference" character varying(100), "refundedAt" TIMESTAMP WITH TIME ZONE, CONSTRAINT "UQ_424cbc15e555622e94842e9a303" UNIQUE ("returnNumber"), CONSTRAINT "PK_27a2f1895a71519ebfec7850361" PRIMARY KEY ("id"))`);
        await queryRunner.query(`CREATE UNIQUE INDEX "IDX_424cbc15e555622e94842e9a30" ON "returns" ("returnNumber") `);
        await queryRunner.query(`CREATE INDEX "IDX_b3851bc6d0e2a7ddc7412806a0" ON "returns" ("orderId") `);
        await queryRunner.query(`CREATE INDEX "IDX_83a410bee35579124b2e3fd300" ON "returns" ("orderItemId") `);
        await queryRunner.query(`CREATE INDEX "IDX_9b0347fc223481c472166d3501" ON "returns" ("buyerId") `);
        await queryRunner.query(`CREATE INDEX "IDX_8a925f640951c8be5943defb70" ON "returns" ("sellerId") `);
        await queryRunner.query(`CREATE INDEX "IDX_586e9208b6ccacb7a2e81ba8e5" ON "returns" ("status") `);
        await queryRunner.query(`ALTER TABLE "returns" ADD CONSTRAINT "FK_b3851bc6d0e2a7ddc7412806a0f" FOREIGN KEY ("orderId") REFERENCES "orders"("id") ON DELETE CASCADE ON UPDATE NO ACTION`);
        await queryRunner.query(`ALTER TABLE "returns" ADD CONSTRAINT "FK_83a410bee35579124b2e3fd3001" FOREIGN KEY ("orderItemId") REFERENCES "order_items"("id") ON DELETE CASCADE ON UPDATE NO ACTION`);
    }

    public async down(queryRunner: QueryRunner): Promise<void> {
        await queryRunner.query(`ALTER TABLE "returns" DROP CONSTRAINT "FK_83a410bee35579124b2e3fd3001"`);
        await queryRunner.query(`ALTER TABLE "returns" DROP CONSTRAINT "FK_b3851bc6d0e2a7ddc7412806a0f"`);
        await queryRunner.query(`DROP INDEX "public"."IDX_586e9208b6ccacb7a2e81ba8e5"`);
        await queryRunner.query(`DROP INDEX "public"."IDX_8a925f640951c8be5943defb70"`);
        await queryRunner.query(`DROP INDEX "public"."IDX_9b0347fc223481c472166d3501"`);
        await queryRunner.query(`DROP INDEX "public"."IDX_83a410bee35579124b2e3fd300"`);
        await queryRunner.query(`DROP INDEX "public"."IDX_b3851bc6d0e2a7ddc7412806a0"`);
        await queryRunner.query(`DROP INDEX "public"."IDX_424cbc15e555622e94842e9a30"`);
        await queryRunner.query(`DROP TABLE "returns"`);
        await queryRunner.query(`DROP TYPE "public"."returns_refundmethod_enum"`);
        await queryRunner.query(`DROP TYPE "public"."returns_status_enum"`);
        await queryRunner.query(`DROP TYPE "public"."returns_reason_enum"`);
    }

}
