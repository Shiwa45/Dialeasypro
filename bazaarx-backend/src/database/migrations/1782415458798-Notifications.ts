import { MigrationInterface, QueryRunner } from "typeorm";

export class Notifications1782415458798 implements MigrationInterface {
    name = 'Notifications1782415458798'

    public async up(queryRunner: QueryRunner): Promise<void> {
        await queryRunner.query(`CREATE TYPE "public"."notifications_type_enum" AS ENUM('order_placed', 'payment_success', 'payment_failed', 'order_shipped', 'order_delivered', 'return_requested', 'return_approved', 'refund_processed', 'seller_new_order')`);
        await queryRunner.query(`CREATE TABLE "notifications" ("id" uuid NOT NULL DEFAULT uuid_generate_v4(), "createdAt" TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT now(), "updatedAt" TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT now(), "deletedAt" TIMESTAMP WITH TIME ZONE, "userId" uuid NOT NULL, "type" "public"."notifications_type_enum" NOT NULL, "title" character varying(200) NOT NULL, "body" character varying(1000) NOT NULL, "data" jsonb NOT NULL DEFAULT '{}', "isRead" boolean NOT NULL DEFAULT false, "readAt" TIMESTAMP WITH TIME ZONE, CONSTRAINT "PK_6a72c3c0f683f6462415e653c3a" PRIMARY KEY ("id"))`);
        await queryRunner.query(`CREATE INDEX "IDX_692a909ee0fa9383e7859f9b40" ON "notifications" ("userId") `);
        await queryRunner.query(`CREATE INDEX "IDX_8ba28344602d583583b9ea1a50" ON "notifications" ("isRead") `);
        await queryRunner.query(`CREATE TABLE "notification_preferences" ("id" uuid NOT NULL DEFAULT uuid_generate_v4(), "createdAt" TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT now(), "updatedAt" TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT now(), "deletedAt" TIMESTAMP WITH TIME ZONE, "userId" uuid NOT NULL, "sms" boolean NOT NULL DEFAULT true, "email" boolean NOT NULL DEFAULT true, "push" boolean NOT NULL DEFAULT true, CONSTRAINT "UQ_b70c44e8b00757584a393225593" UNIQUE ("userId"), CONSTRAINT "PK_e94e2b543f2f218ee68e4f4fad2" PRIMARY KEY ("id"))`);
        await queryRunner.query(`CREATE UNIQUE INDEX "IDX_b70c44e8b00757584a39322559" ON "notification_preferences" ("userId") `);
    }

    public async down(queryRunner: QueryRunner): Promise<void> {
        await queryRunner.query(`DROP INDEX "public"."IDX_b70c44e8b00757584a39322559"`);
        await queryRunner.query(`DROP TABLE "notification_preferences"`);
        await queryRunner.query(`DROP INDEX "public"."IDX_8ba28344602d583583b9ea1a50"`);
        await queryRunner.query(`DROP INDEX "public"."IDX_692a909ee0fa9383e7859f9b40"`);
        await queryRunner.query(`DROP TABLE "notifications"`);
        await queryRunner.query(`DROP TYPE "public"."notifications_type_enum"`);
    }

}
