import {
  Inject,
  Injectable,
  BadRequestException,
  NotFoundException,
} from '@nestjs/common';
import { InjectRepository } from '@nestjs/typeorm';
import { DataSource, EntityManager, Repository } from 'typeorm';
import Redis from 'ioredis';
import { REDIS_CLIENT } from '../../../database/redis.module';
import {
  Wallet,
  WalletTransaction,
  WalletTxnType,
  WalletTxnSource,
  BnplAccount,
} from '../entities/wallet.entity';
import { RazorpayService } from '../../payments/services/razorpay.service';
import { paginate } from '../../../common/dto/paginated-result';
import { PaginationQueryDto } from '../../../common/dto/pagination-query.dto';

const TOPUP_TTL = 3600; // 1h to complete a topup

@Injectable()
export class WalletService {
  constructor(
    @InjectRepository(Wallet)
    private readonly walletRepo: Repository<Wallet>,
    @InjectRepository(WalletTransaction)
    private readonly txnRepo: Repository<WalletTransaction>,
    @InjectRepository(BnplAccount)
    private readonly bnplRepo: Repository<BnplAccount>,
    @Inject(REDIS_CLIENT) private readonly redis: Redis,
    private readonly razorpay: RazorpayService,
    private readonly dataSource: DataSource,
  ) {}

  // -------- Wallet basics --------

  async getOrCreate(userId: string): Promise<Wallet> {
    let wallet = await this.walletRepo.findOne({ where: { userId } });
    if (!wallet) {
      wallet = await this.walletRepo.save(this.walletRepo.create({ userId }));
    }
    return wallet;
  }

  async balance(userId: string): Promise<number> {
    return (await this.getOrCreate(userId)).balance;
  }

  async history(userId: string, query: PaginationQueryDto) {
    const wallet = await this.getOrCreate(userId);
    const [items, total] = await this.txnRepo.findAndCount({
      where: { walletId: wallet.id },
      order: { createdAt: 'DESC' },
      skip: query.offset,
      take: query.limit,
    });
    return paginate(items, total, query.page, query.limit, 'Transactions');
  }

  /** Credits the wallet (own transaction). */
  async credit(
    userId: string,
    amount: number,
    source: WalletTxnSource,
    reference?: string,
    description?: string,
  ): Promise<WalletTransaction> {
    return this.dataSource.transaction((m) =>
      this.creditTx(m, userId, amount, source, reference, description),
    );
  }

  /** Debits the wallet (own transaction); throws on insufficient funds. */
  async debit(
    userId: string,
    amount: number,
    source: WalletTxnSource,
    reference?: string,
    description?: string,
  ): Promise<WalletTransaction> {
    return this.dataSource.transaction((m) =>
      this.debitTx(m, userId, amount, source, reference, description),
    );
  }

  /** Credit within an existing transaction (for checkout/return flows). */
  async creditTx(
    manager: EntityManager,
    userId: string,
    amount: number,
    source: WalletTxnSource,
    reference?: string,
    description?: string,
  ): Promise<WalletTransaction> {
    if (amount <= 0) throw new BadRequestException('Amount must be positive');
    const wallet = await this.lockWallet(manager, userId);
    wallet.balance += amount;
    await manager.save(wallet);
    return manager.save(
      manager.create(WalletTransaction, {
        walletId: wallet.id,
        type: WalletTxnType.CREDIT,
        source,
        amount,
        balanceAfter: wallet.balance,
        reference,
        description,
      }),
    );
  }

  /** Debit within an existing transaction. */
  async debitTx(
    manager: EntityManager,
    userId: string,
    amount: number,
    source: WalletTxnSource,
    reference?: string,
    description?: string,
  ): Promise<WalletTransaction> {
    if (amount <= 0) throw new BadRequestException('Amount must be positive');
    const wallet = await this.lockWallet(manager, userId);
    if (wallet.balance < amount) {
      throw new BadRequestException('Insufficient wallet balance');
    }
    wallet.balance -= amount;
    await manager.save(wallet);
    return manager.save(
      manager.create(WalletTransaction, {
        walletId: wallet.id,
        type: WalletTxnType.DEBIT,
        source,
        amount,
        balanceAfter: wallet.balance,
        reference,
        description,
      }),
    );
  }

  // -------- Top-up (Razorpay) --------

  async initiateTopup(userId: string, amount: number) {
    if (amount < 1000) {
      throw new BadRequestException('Minimum top-up is ₹10');
    }
    const gw = await this.razorpay.createOrder(amount, `WALLET-${userId.slice(0, 8)}`);
    await this.redis.set(
      `wallet:topup:${gw.gatewayOrderId}`,
      JSON.stringify({ userId, amount }),
      'EX',
      TOPUP_TTL,
    );
    return gw;
  }

  async verifyTopup(
    userId: string,
    gatewayOrderId: string,
    gatewayPaymentId: string,
    signature: string,
  ) {
    const key = `wallet:topup:${gatewayOrderId}`;
    const stored = await this.redis.get(key);
    if (!stored) throw new NotFoundException('Top-up session expired');
    const { userId: owner, amount } = JSON.parse(stored);
    if (owner !== userId) throw new BadRequestException('Not your top-up');

    if (!this.razorpay.verifyPaymentSignature(gatewayOrderId, gatewayPaymentId, signature)) {
      throw new BadRequestException('Invalid payment signature');
    }
    await this.redis.del(key);
    const txn = await this.credit(
      userId,
      amount,
      WalletTxnSource.TOPUP,
      gatewayOrderId,
      'Wallet top-up',
    );
    return { balance: txn.balanceAfter, credited: amount };
  }

  /** DEV: simulate a successful top-up payment (mock mode only). */
  async mockPayTopup(userId: string, gatewayOrderId: string) {
    if (!this.razorpay.isMock) {
      throw new BadRequestException('Mock payments are disabled');
    }
    const paymentId = `pay_MOCK${gatewayOrderId.slice(-8)}`;
    const sig = this.razorpay.mockSignPayment(gatewayOrderId, paymentId);
    return this.verifyTopup(userId, gatewayOrderId, paymentId, sig);
  }

  // -------- BNPL --------

  async getBnpl(userId: string): Promise<BnplAccount> {
    let acc = await this.bnplRepo.findOne({ where: { userId } });
    if (!acc) {
      acc = await this.bnplRepo.save(this.bnplRepo.create({ userId }));
    }
    return acc;
  }

  /** Charges the BNPL line within a transaction (checkout). */
  async bnplChargeTx(
    manager: EntityManager,
    userId: string,
    amount: number,
    reference?: string,
  ): Promise<void> {
    const acc = await manager.findOne(BnplAccount, {
      where: { userId },
      lock: { mode: 'pessimistic_write' },
    });
    const account = acc ?? (await manager.save(manager.create(BnplAccount, { userId })));
    if (!account.isActive) throw new BadRequestException('BNPL is not available');
    if (account.used + amount > account.creditLimit) {
      throw new BadRequestException('BNPL credit limit exceeded');
    }
    account.used += amount;
    await manager.save(account);
  }

  /** Repays BNPL from the wallet balance. */
  async repayBnpl(userId: string, amount: number) {
    return this.dataSource.transaction(async (m) => {
      const acc = await m.findOne(BnplAccount, {
        where: { userId },
        lock: { mode: 'pessimistic_write' },
      });
      if (!acc || acc.used === 0) {
        throw new BadRequestException('Nothing to repay');
      }
      const repay = Math.min(amount, acc.used);
      await this.debitTx(
        m,
        userId,
        repay,
        WalletTxnSource.BNPL_REPAYMENT,
        undefined,
        'BNPL repayment',
      );
      acc.used -= repay;
      await m.save(acc);
      return { repaid: repay, outstanding: acc.used };
    });
  }

  private async lockWallet(
    manager: EntityManager,
    userId: string,
  ): Promise<Wallet> {
    let wallet = await manager.findOne(Wallet, {
      where: { userId },
      lock: { mode: 'pessimistic_write' },
    });
    if (!wallet) {
      wallet = await manager.save(manager.create(Wallet, { userId }));
    }
    return wallet;
  }
}
