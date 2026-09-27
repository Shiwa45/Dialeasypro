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
// DialEasypro — Auto Dial home
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
      AppToast.show(context, 'Finish the current call before taking a break', isError: true);
    }
  }

  @override
  Widget build(BuildContext context) {
    final work = ref.watch(workSessionProvider);
    final elapsed = Fmt.timer(DateTime.now().difference(work.since).inSeconds);
    final onBreak = work.onBreak;

    return BrutalCard(
      padding: const EdgeInsets.all(14),
      color: onBreak ? AppColors.warningBg : AppColors.successBg,
      borderColor: onBreak ? AppColors.warning : AppColors.success,
      child: Row(children: [
        Container(
          width: 10, height: 10,
          decoration: BoxDecoration(
            color: onBreak ? AppColors.warning : AppColors.success,
            shape: BoxShape.circle,
          ),
        ),
        const SizedBox(width: 10),
        Expanded(child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
          Text(
            !work.live ? 'Connecting…' : onBreak ? 'On break' : 'Live · Available',
            style: AppTextStyles.h5,
          ),
          const SizedBox(height: 2),
          Text(
            onBreak
                ? '${work.breakReason.isEmpty ? 'Break' : work.breakReason} · $elapsed'
                : 'Idle $elapsed · take a break to open leads, manual calls or WhatsApp',
            style: AppTextStyles.caption,
          ),
        ])),
        const SizedBox(width: 8),
        BrutalButton(
          label: onBreak ? 'END BREAK' : 'BREAK',
          iconData: onBreak ? Icons.play_arrow : Icons.free_breakfast,
          backgroundColor: onBreak ? AppColors.success : AppColors.purple,
          textColor: AppColors.white,
          onPressed: !work.live
              ? null
              : onBreak
                  ? () => ref.read(workSessionProvider.notifier).endBreak()
                  : _takeBreak,
        ),
      ]),
    );
  }
}
