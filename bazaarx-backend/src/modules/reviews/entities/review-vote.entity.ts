import { Entity, Column, Index, ManyToOne, JoinColumn } from 'typeorm';
import { BaseEntity } from '../../../common/entities/base.entity';
import { Review } from './review.entity';

/**
 * One "helpful" vote per user per review (unique), so a user can't
 * inflate a review's helpful count by voting repeatedly.
 */
@Entity('review_votes')
@Index(['reviewId', 'userId'], { unique: true })
export class ReviewVote extends BaseEntity {
  @ManyToOne(() => Review, { onDelete: 'CASCADE', nullable: false })
  @JoinColumn({ name: 'reviewId' })
  review: Review;

  @Column({ type: 'uuid' })
  reviewId: string;

  @Index()
  @Column({ type: 'uuid' })
  userId: string;
}
