import 'dart:async';

import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:go_router/go_router.dart';

import '../../core/theme/colors.dart';
import '../../core/utils/utils.dart';
import '../../core/widgets/widgets.dart';
import '../work/work_session.dart';
import 'dialer_state.dart';
import 'queue_starter_screen.dart';

// ============================================================
// DialSathi — Auto Dial home
//
// Where the app opens after sign-in. The agent is live from the moment they
// land here; the strip at the top says so and counts idle time. The rest of
// the app is behind a break.
// ============================================================

class AutoDialHome extends ConsumerWidget {
  const AutoDialHome({super.key});

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final dialer = ref.watch(dialerProvider);
    return QueueStarterScreen(
      embedded: true,
      header: Column(children: [
        const WorkStatusStrip(),
        // A queue left running (the agent backed out of the dialer screen
        // mid-queue) is one tap from being picked up again.
        if (dialer.mode == DialerMode.queue && dialer.phase != DialerPhase.completed) ...[
          const SizedBox(height: 12),
          BrutalButton(
            label: 'RETURN TO ACTIVE QUEUE',
            iconData: Icons.play_arrow,
            backgroundColor: AppColors.success,
            textColor: AppColors.white,
            isFullWidth: true,
            onPressed: () => context.push('/dialer'),
          ),
        ],
      ]),
      actions: [
        IconButton(
          tooltip: 'Profile',
          icon: const Icon(Icons.person_outline),
          onPressed: () => context.push('/profile'),
        ),
      ],
    );
  }
}

/// "● Live · Available · idle 03:12" with a BREAK button, or the break
/// equivalent with END BREAK.
class WorkStatusStrip extends ConsumerStatefulWidget {
  const WorkStatusStrip({super.key});

  @override
  ConsumerState<WorkStatusStrip> createState() => _WorkStatusStripState();
}

class _WorkStatusStripState extends ConsumerState<WorkStatusStrip> {
  Timer? _tick;

  @override
  void initState() {
    super.initState();
    _tick = Timer.periodic(const Duration(seconds: 1), (_) {
      if (mounted) setState(() {});
    });
  }

  @override
  void dispose() {
    _tick?.cancel();
    super.dispose();
  }

  Future<void> _takeBreak() async {
    final reason = await showModalBottomSheet<String>(
      context: context,
      builder: (ctx) => SafeArea(
        child: Column(mainAxisSize: MainAxisSize.min, children: [
          const Padding(
            padding: EdgeInsets.fromLTRB(16, 16, 16, 8),
            child: Text('Take a break', style: AppTextStyles.h4),
          ),
          for (final r in breakReasons)
            ListTile(
              leading: const Icon(Icons.free_breakfast_outlined),
              title: Text(r),
              onTap: () => Navigator.of(ctx).pop(r),
            ),
          const SizedBox(height: 8),
        ]),
      ),
    );
    if (reason == null || !mounted) return;
    final ok = await ref.read(workSessionProvider.notifier).takeBreak(reason: reason);
    if (!ok && mounted) {
      AppToast.show(context, 'Finish the current call and save its outcome before taking a break',
          isError: true);
    }
  }

  @override
  Widget build(BuildContext context) {
    final work = ref.watch(workSessionProvider);
    final elapsed = Fmt.timer(DateTime.now().difference(work.since).inSeconds);
    final onBreak = work.onBreak;
    final VoidCallback? onPressed = !work.live
        ? null
        : onBreak
            ? () => ref.read(workSessionProvider.notifier).endBreak()
            : _takeBreak;

    final statusLabel = !work.live ? 'CONNECTING' : onBreak ? 'ON BREAK' : 'LIVE · AVAILABLE';
    final statusColor = !work.live ? AppColors.line3 : onBreak ? AppColors.amber : AppColors.mint2;

    return Container(
      padding: const EdgeInsets.fromLTRB(18, 16, 18, 18),
      decoration: BoxDecoration(
        borderRadius: BorderRadius.circular(20),
        gradient: LinearGradient(
          begin: Alignment.topLeft,
          end: Alignment.bottomRight,
          colors: onBreak
              ? const [Color(0xFF3B2A05), Color(0xFF5C420A)]
              : const [AppColors.ink, AppColors.ink2],
        ),
        boxShadow: [
          BoxShadow(color: AppColors.ink.withValues(alpha: 0.18), blurRadius: 20, offset: const Offset(0, 6)),
        ],
      ),
      child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
        Row(children: [
          // ---- Status pill ----
          Container(
            padding: const EdgeInsets.symmetric(horizontal: 10, vertical: 5),
            decoration: BoxDecoration(
              color: statusColor.withValues(alpha: 0.16),
              borderRadius: BorderRadius.circular(999),
              border: Border.all(color: statusColor.withValues(alpha: 0.45)),
            ),
            child: Row(mainAxisSize: MainAxisSize.min, children: [
              Container(
                width: 7, height: 7,
                decoration: BoxDecoration(color: statusColor, shape: BoxShape.circle),
              ),
              const SizedBox(width: 6),
              Text(statusLabel, style: AppTextStyles.label.copyWith(fontSize: 10, color: statusColor)),
            ]),
          ),
          const Spacer(),
          // ---- Break / End break ----
          TextButton.icon(
            onPressed: onPressed,
            icon: Icon(onBreak ? Icons.play_arrow_rounded : Icons.free_breakfast_outlined, size: 18),
            label: Text(onBreak ? 'End break' : 'Take break'),
            style: TextButton.styleFrom(
              foregroundColor: onBreak ? AppColors.mintInk : AppColors.white,
              backgroundColor: onBreak ? AppColors.mint : AppColors.white.withValues(alpha: 0.12),
              disabledForegroundColor: AppColors.white.withValues(alpha: 0.4),
              textStyle: AppTextStyles.button.copyWith(fontSize: 13),
              padding: const EdgeInsets.symmetric(horizontal: 14, vertical: 8),
              minimumSize: const Size(0, 36),
              shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(999)),
            ),
          ),
        ]),
        const SizedBox(height: 16),
        // ---- Timer ----
        Text(
          onBreak ? (work.breakReason.isEmpty ? 'Break time' : work.breakReason) : 'Idle time',
          style: AppTextStyles.caption.copyWith(color: AppColors.white.withValues(alpha: 0.7)),
        ),
        const SizedBox(height: 2),
        Text(
          elapsed,
          style: AppTextStyles.monoLg.copyWith(fontSize: 40, letterSpacing: -1, color: AppColors.white, height: 1.1),
        ),
        const SizedBox(height: 10),
        Text(
          onBreak
              ? 'Leads, manual calls and WhatsApp are open. End your break to auto-dial.'
              : 'Pick a queue below to start dialling. Take a break to open leads, manual calls or WhatsApp.',
          style: AppTextStyles.caption.copyWith(color: AppColors.white.withValues(alpha: 0.65), fontSize: 11.5),
        ),
      ]),
    );
  }
}
