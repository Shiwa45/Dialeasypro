import { MigrationInterface, QueryRunner } from "typeorm";

export class Wallet1782480210101 implements MigrationInterface {
    name = 'Wallet1782480210101'

    public async up(queryRunner: QueryRunner): Promise<void> {
        await queryRunner.query(`CREATE TABLE "wallets" ("id" uuid NOT NULL DEFAULT uuid_generate_v4(), "createdAt" TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT now(), "updatedAt" TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT now(), "deletedAt" TIMESTAMP WITH TIME ZONE, "userId" uuid NOT NULL, "balance" bigint NOT NULL DEFAULT '0', CONSTRAINT "UQ_2ecdb33f23e9a6fc392025c0b97" UNIQUE ("userId"), CONSTRAINT "PK_8402e5df5a30a229380e83e4f7e" PRIMARY KEY ("id"))`);
        await queryRunner.query(`CREATE UNIQUE INDEX "IDX_2ecdb33f23e9a6fc392025c0b9" ON "wallets" ("userId") `);
        await queryRunner.query(`CREATE TYPE "public"."wallet_transactions_type_enum" AS ENUM('credit', 'debit')`);
        await queryRunner.query(`CREATE TYPE "public"."wallet_transactions_source_enum" AS ENUM('topup', 'refund', 'purchase', 'cashback', 'bnpl_repayment', 'reversal')`);
        await queryRunner.query(`CREATE TABLE "wallet_transactions" ("id" uuid NOT NULL DEFAULT uuid_generate_v4(), "createdAt" TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT now(), "updatedAt" TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT now(), "deletedAt" TIMESTAMP WITH TIME ZONE, "walletId" uuid NOT NULL, "type" "public"."wallet_transactions_type_enum" NOT NULL, "source" "public"."wallet_transactions_source_enum" NOT NULL, "amount" integer NOT NULL, "balanceAfter" bigint NOT NULL, "description" character varying(200), "reference" character varying(100), CONSTRAINT "PK_5120f131bde2cda940ec1a621db" PRIMARY KEY ("id"))`);
        await queryRunner.query(`CREATE INDEX "IDX_8a94d9d61a2b05123710b325fb" ON "wallet_transactions" ("walletId") `);
        await queryRunner.query(`CREATE TABLE "bnpl_accounts" ("id" uuid NOT NULL DEFAULT uuid_generate_v4(), "createdAt" TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT now(), "updatedAt" TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT now(), "deletedAt" TIMESTAMP WITH TIME ZONE, "userId" uuid NOT NULL, "creditLimit" integer NOT NULL DEFAULT '2000000', "used" integer NOT NULL DEFAULT '0', "isActive" boolean NOT NULL DEFAULT true, CONSTRAINT "UQ_36ad1004b3eb60fb6f0127cb1fb" UNIQUE ("userId"), CONSTRAINT "PK_5c0a447b86790ff91b0ad8bd9c7" PRIMARY KEY ("id"))`);
        await queryRunner.query(`CREATE UNIQUE INDEX "IDX_36ad1004b3eb60fb6f0127cb1f" ON "bnpl_accounts" ("userId") `);
        await queryRunner.query(`ALTER TYPE "public"."orders_paymentmethod_enum" RENAME TO "orders_paymentmethod_enum_old"`);
        await queryRunner.query(`CREATE TYPE "public"."orders_paymentmethod_enum" AS ENUM('cod', 'upi', 'card', 'netbanking', 'wallet', 'bnpl')`);
        await queryRunner.query(`ALTER TABLE "orders" ALTER COLUMN "paymentMethod" TYPE "public"."orders_paymentmethod_enum" USING "paymentMethod"::"text"::"public"."orders_paymentmethod_enum"`);
        await queryRunner.query(`DROP TYPE "public"."orders_paymentmethod_enum_old"`);
        await queryRunner.query(`ALTER TABLE "wallet_transactions" ADD CONSTRAINT "FK_8a94d9d61a2b05123710b325fbf" FOREIGN KEY ("walletId") REFERENCES "wallets"("id") ON DELETE CASCADE ON UPDATE NO ACTION`);
    }

    public async down(queryRunner: QueryRunner): Promise<void> {
        await queryRunner.query(`ALTER TABLE "wallet_transactions" DROP CONSTRAINT "FK_8a94d9d61a2b05123710b325fbf"`);
        await queryRunner.query(`CREATE TYPE "public"."orders_paymentmethod_enum_old" AS ENUM('cod', 'upi', 'card', 'netbanking', 'wallet')`);
        await queryRunner.query(`ALTER TABLE "orders" ALTER COLUMN "paymentMethod" TYPE "public"."orders_paymentmethod_enum_old" USING "paymentMethod"::"text"::"public"."orders_paymentmethod_enum_old"`);
        await queryRunner.query(`DROP TYPE "public"."orders_paymentmethod_enum"`);
        await queryRunner.query(`ALTER TYPE "public"."orders_paymentmethod_enum_old" RENAME TO "orders_paymentmethod_enum"`);
        await queryRunner.query(`DROP INDEX "public"."IDX_36ad1004b3eb60fb6f0127cb1f"`);
        await queryRunner.query(`DROP TABLE "bnpl_accounts"`);
        await queryRunner.query(`DROP INDEX "public"."IDX_8a94d9d61a2b05123710b325fb"`);
        await queryRunner.query(`DROP TABLE "wallet_transactions"`);
        await queryRunner.query(`DROP TYPE "public"."wallet_transactions_source_enum"`);
        await queryRunner.query(`DROP TYPE "public"."wallet_transactions_type_enum"`);
        await queryRunner.query(`DROP INDEX "public"."IDX_2ecdb33f23e9a6fc392025c0b9"`);
        await queryRunner.query(`DROP TABLE "wallets"`);
    }

}
