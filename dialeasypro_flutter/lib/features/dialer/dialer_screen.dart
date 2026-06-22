import 'package:flutter/material.dart';
import 'package:flutter/services.dart';
import 'package:flutter_animate/flutter_animate.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:go_router/go_router.dart';
import '../../core/services/phone_service.dart';
import '../../core/services/whatsapp_service.dart';
import '../../core/services/recording_service.dart';
import '../../core/theme/colors.dart';
import '../../core/utils/utils.dart';
import '../../core/widgets/widgets.dart';
import '../../data/models/models.dart';
import '../../data/services/services.dart';
import 'dialer_state.dart';

// ============================================================
// DialEasypro — Active Dialer Screen
// Full-screen experience for the auto-dialer flow:
//  - Pre-call: lead preview + countdown
//  - In-call: live timer + notes + quick actions
//  - Post-call: MANDATORY disposition before next
//  - Completed: queue summary
// ============================================================

class DialerScreen extends ConsumerStatefulWidget {
  const DialerScreen({super.key});

  @override
  ConsumerState<DialerScreen> createState() => _DialerScreenState();
}

class _DialerScreenState extends ConsumerState<DialerScreen> {
  @override
  Widget build(BuildContext context) {
    final state = ref.watch(dialerProvider);

    return WillPopScope(
      onWillPop: () async {
        if (state.phase == DialerPhase.postCall) {
          AppToast.show(context, 'Please dispose this call first', isError: true);
          return false;
        }
        if (state.mode == DialerMode.queue && state.phase != DialerPhase.completed) {
          final confirmed = await showBrutalConfirm(
            context: context,
            title: 'Stop Auto-Dialer?',
            message: 'You will exit the queue. Progress will be lost.',
            confirmLabel: 'Stop & Exit',
            danger: true,
          );
          if (confirmed == true) {
            ref.read(dialerProvider.notifier).stop();
            return true;
          }
          return false;
        }
        ref.read(dialerProvider.notifier).stop();
        return true;
      },
      child: Scaffold(
        backgroundColor: AppColors.background,
        body: SafeArea(
          child: Column(
            children: [
              _TopBar(state: state),
              if (state.mode == DialerMode.queue) _QueueProgress(state: state),
              Expanded(child: _PhaseContent(state: state)),
            ],
          ),
        ),
      ),
    );
  }
}

// ─── TOP BAR ────────────────────────────────────────────────
class _TopBar extends ConsumerWidget {
  final DialerState state;
  const _TopBar({required this.state});

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    return Container(
      padding: const EdgeInsets.symmetric(horizontal: 12, vertical: 8),
      decoration: const BoxDecoration(
        color: AppColors.dark,
        border: Border(bottom: BorderSide(color: AppColors.black, width: 2)),
      ),
      child: Row(children: [
        IconButton(
          icon: const Icon(Icons.close, color: AppColors.white),
          onPressed: () async {
            if (state.phase == DialerPhase.postCall) {
              AppToast.show(context, 'Please dispose this call first', isError: true);
              return;
            }
            final canStop = state.mode != DialerMode.queue ||
                            state.phase == DialerPhase.completed ||
                            (await showBrutalConfirm(
                              context: context,
                              title: 'Exit Dialer?',
                              message: 'The auto-dialer queue will be stopped.',
                              confirmLabel: 'Exit',
                              danger: true,
                            )) == true;
            if (canStop && context.mounted) {
              ref.read(dialerProvider.notifier).stop();
              context.pop();
            }
          },
        ),
        const SizedBox(width: 4),
        Container(
          padding: const EdgeInsets.symmetric(horizontal: 8, vertical: 3),
          decoration: BoxDecoration(
            color: AppColors.yellow,
            border: Border.all(color: AppColors.black, width: 1.5),
          ),
          child: const Text('AUTO-DIALER',
              style: TextStyle(fontFamily: 'SpaceGrotesk', fontWeight: FontWeight.w700, fontSize: 10, letterSpacing: 0.6)),
        ),
        const Spacer(),
        if (state.phase == DialerPhase.inCall || state.phase == DialerPhase.dialing)
          _LivePulse(),
        // Break toggle — only between calls (not while dialing or in a call).
        if (state.mode == DialerMode.queue &&
            state.phase != DialerPhase.inCall &&
            state.phase != DialerPhase.dialing) ...[
          const SizedBox(width: 8),
          GestureDetector(
            onTap: () {
              final notifier = ref.read(dialerProvider.notifier);
              if (state.onBreak) {
                notifier.endBreak();
              } else {
                notifier.goOnBreak();
              }
            },
            child: Container(
              padding: const EdgeInsets.symmetric(horizontal: 8, vertical: 5),
              decoration: BoxDecoration(
                color: state.onBreak ? AppColors.success : AppColors.purple,
                border: Border.all(color: AppColors.black, width: 1.5),
              ),
              child: Row(mainAxisSize: MainAxisSize.min, children: [
                Icon(state.onBreak ? Icons.play_arrow : Icons.free_breakfast,
                    size: 14, color: AppColors.white),
                const SizedBox(width: 4),
                Text(state.onBreak ? 'END BREAK' : 'BREAK',
                    style: const TextStyle(fontFamily: 'SpaceGrotesk', fontWeight: FontWeight.w700, fontSize: 10, color: AppColors.white, letterSpacing: 0.4)),
              ]),
            ),
          ),
        ],
        if (state.mode == DialerMode.queue &&
            !state.onBreak &&
            state.phase != DialerPhase.completed &&
            state.phase != DialerPhase.postCall) ...[
          const SizedBox(width: 8),
          GestureDetector(
            onTap: () {
              if (state.phase == DialerPhase.paused) {
                ref.read(dialerProvider.notifier).resume();
              } else {
                ref.read(dialerProvider.notifier).pause();
              }
            },
            child: Container(
              padding: const EdgeInsets.all(6),
              decoration: BoxDecoration(
                color: state.phase == DialerPhase.paused ? AppColors.success : AppColors.warning,
                border: Border.all(color: AppColors.black, width: 1.5),
              ),
              child: Icon(
                state.phase == DialerPhase.paused ? Icons.play_arrow : Icons.pause,
                size: 16, color: AppColors.white,
              ),
            ),
          ),
        ],
      ]),
    );
  }
}

class _LivePulse extends StatelessWidget {
  @override
  Widget build(BuildContext context) {
    return Row(children: [
      Container(
        width: 8, height: 8,
        decoration: const BoxDecoration(color: AppColors.error, shape: BoxShape.circle),
      ).animate(onPlay: (c) => c.repeat()).fade(begin: 1, end: 0.3, duration: 800.ms),
      const SizedBox(width: 6),
      const Text('LIVE',
          style: TextStyle(fontFamily: 'SpaceGrotesk', fontWeight: FontWeight.w700, fontSize: 11, color: AppColors.error, letterSpacing: 0.5)),
    ]);
  }
}

// ─── QUEUE PROGRESS ─────────────────────────────────────────
class _QueueProgress extends StatelessWidget {
  final DialerState state;
  const _QueueProgress({required this.state});

  @override
  Widget build(BuildContext context) {
    return Container(
      padding: const EdgeInsets.symmetric(horizontal: 16, vertical: 10),
      decoration: const BoxDecoration(
        color: AppColors.white,
        border: Border(bottom: BorderSide(color: AppColors.black, width: 1.5)),
      ),
      child: Column(children: [
        Row(children: [
          Text(
            '${state.currentIndex + 1} / ${state.totalCalls}',
            style: const TextStyle(fontFamily: 'SpaceGrotesk', fontWeight: FontWeight.w700, fontSize: 14),
          ),
          const SizedBox(width: 10),
          Expanded(
            child: Container(
              height: 10,
              decoration: BoxDecoration(
                color: AppColors.greyLight,
                border: Border.all(color: AppColors.black, width: 1.5),
              ),
              child: FractionallySizedBox(
                alignment: Alignment.centerLeft,
                widthFactor: state.progress,
                child: Container(color: AppColors.yellow),
              ),
            ),
          ),
          const SizedBox(width: 10),
          Text('${(state.progress * 100).toInt()}%',
              style: const TextStyle(fontFamily: 'SpaceGrotesk', fontWeight: FontWeight.w700, fontSize: 12, color: AppColors.grey)),
        ]),
      ]),
    );
  }
}

// ─── PHASE CONTENT (router) ─────────────────────────────────
class _PhaseContent extends StatelessWidget {
  final DialerState state;
  const _PhaseContent({required this.state});

  @override
  Widget build(BuildContext context) {
    switch (state.phase) {
      case DialerPhase.preCall:
      case DialerPhase.dialing:
        return _PreCallView(state: state);
      case DialerPhase.inCall:
        return _InCallView(state: state);
      case DialerPhase.postCall:
        return _DispositionView(state: state);
      case DialerPhase.paused:
        return _PausedView(state: state);
      case DialerPhase.completed:
        return _CompletedView(state: state);
      case DialerPhase.idle:
      case DialerPhase.disposed:
        return const Center(child: CircularProgressIndicator());
    }
  }
}

// ─── PRE-CALL VIEW ──────────────────────────────────────────
class _PreCallView extends ConsumerWidget {
  final DialerState state;
  const _PreCallView({required this.state});

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final lead = state.currentLead;
    if (lead == null) return const SizedBox.shrink();

    final isDialing = state.phase == DialerPhase.dialing;

    return SingleChildScrollView(
      padding: const EdgeInsets.all(20),
      child: Column(children: [
        // Big animated lead card
        Container(
          padding: const EdgeInsets.all(20),
          decoration: BoxDecoration(
            gradient: AppColors.yellowGradient,
            border: Border.all(color: AppColors.black, width: 2.5),
            boxShadow: const [BoxShadow(color: AppColors.black, offset: Offset(6, 6))],
          ),
          child: Column(children: [
            BrutalAvatar(name: lead.name, size: 80),
            const SizedBox(height: 14),
            Text(lead.name, style: AppTextStyles.h1, textAlign: TextAlign.center),
            const SizedBox(height: 4),
            Text(Fmt.displayPhone(lead.phone),
                style: const TextStyle(fontFamily: 'monospace', fontWeight: FontWeight.w700, fontSize: 16, letterSpacing: 0.3)),
            const SizedBox(height: 12),
            Wrap(
              alignment: WrapAlignment.center,
              spacing: 6, runSpacing: 6,
              children: [
                StatusBadge(status: lead.status, label: lead.statusDisplay),
                PriorityBadge(priority: lead.priority),
                if (lead.city.isNotEmpty) TagChip(label: lead.city, backgroundColor: AppColors.white),
                if (lead.isDnd) const TagChip(label: 'DND', backgroundColor: AppColors.error, textColor: AppColors.white),
              ],
            ),
          ]),
        ).animate().scale(begin: const Offset(0.85, 0.85), curve: Curves.easeOutBack, duration: 400.ms),

        const SizedBox(height: 28),

        if (lead.requirement.isNotEmpty) ...[
          BrutalCard(
            padding: const EdgeInsets.all(14),
            color: AppColors.cream,
            child: Row(children: [
              const Icon(Icons.info_outline, size: 16, color: AppColors.warning),
              const SizedBox(width: 8),
              Expanded(child: Text(lead.requirement, style: AppTextStyles.body, maxLines: 3, overflow: TextOverflow.ellipsis)),
            ]),
          ),
          const SizedBox(height: 16),
        ],

        // Status
        if (isDialing) ...[
          Container(
            padding: const EdgeInsets.symmetric(horizontal: 16, vertical: 10),
            decoration: BoxDecoration(
              color: AppColors.successBg,
              border: Border.all(color: AppColors.success, width: 2),
            ),
            child: Row(mainAxisSize: MainAxisSize.min, children: [
              const Icon(Icons.phone_callback, color: AppColors.success, size: 18),
              const SizedBox(width: 10),
              Text(
                'Dialing ${Fmt.displayPhone(lead.phone)}…',
                style: const TextStyle(fontFamily: 'SpaceGrotesk', fontWeight: FontWeight.w700, fontSize: 13, color: AppColors.success),
              ),
            ]),
          ).animate(onPlay: (c) => c.repeat(reverse: true)).fade(begin: 1, end: 0.5, duration: 1.seconds),
        ] else ...[
          BrutalButton(
            label: 'CALL NOW',
            iconData: Icons.phone,
            backgroundColor: AppColors.success,
            textColor: AppColors.white,
            isFullWidth: true,
            shadowOffset: 5,
            onPressed: () => ref.read(dialerProvider.notifier).dialCurrent(),
          ),
        ],

        const SizedBox(height: 12),

        Row(children: [
          Expanded(child: BrutalButton.secondary(
            label: 'SKIP',
            iconData: Icons.skip_next,
            isFullWidth: true,
            onPressed: () => ref.read(dialerProvider.notifier).skip(),
          )),
          if (state.mode == DialerMode.queue) ...[
            const SizedBox(width: 10),
            Expanded(child: BrutalButton.yellow(
              label: 'PAUSE',
              iconData: Icons.pause,
              isFullWidth: true,
              onPressed: () => ref.read(dialerProvider.notifier).pause(),
            )),
          ],
        ]),
      ]),
    );
  }
}

// ─── IN-CALL VIEW ───────────────────────────────────────────
class _InCallView extends ConsumerStatefulWidget {
  final DialerState state;
  const _InCallView({required this.state});

  @override
  ConsumerState<_InCallView> createState() => _InCallViewState();
}

class _InCallViewState extends ConsumerState<_InCallView> {
  final _notesCtrl = TextEditingController();
  bool _isRecordingNote = false;
  String? _voiceNotePath;

  @override
  void dispose() {
    _notesCtrl.dispose();
    super.dispose();
  }

  Future<void> _toggleRecording() async {
    if (_isRecordingNote) {
      final path = await VoiceRecorderService.instance.stop();
      setState(() {
        _isRecordingNote = false;
        _voiceNotePath = path;
      });
      if (mounted && path != null) AppToast.show(context, 'Voice note saved', isSuccess: true);
    } else {
      final ok = await VoiceRecorderService.instance.start();
      if (ok) setState(() => _isRecordingNote = true);
      else if (mounted) AppToast.show(context, 'Microphone permission required', isError: true);
    }
  }

  @override
  Widget build(BuildContext context) {
    final lead = widget.state.currentLead;
    final call = widget.state.currentCall;
    if (lead == null || call == null) return const SizedBox.shrink();

    return StreamBuilder<PhoneCallEvent>(
      stream: PhoneService.instance.events,
      builder: (ctx, snap) {
        final duration = snap.data?.durationSec ?? call.durationSec;
        return SingleChildScrollView(
          padding: const EdgeInsets.all(20),
          child: Column(children: [
            // Big timer card
            Container(
              padding: const EdgeInsets.all(24),
              decoration: BoxDecoration(
                gradient: AppColors.successGradient,
                border: Border.all(color: AppColors.black, width: 2.5),
                boxShadow: const [BoxShadow(color: AppColors.black, offset: Offset(6, 6))],
              ),
              child: Column(children: [
                Row(mainAxisAlignment: MainAxisAlignment.center, children: const [
                  Icon(Icons.phone_in_talk, color: AppColors.white, size: 18),
                  SizedBox(width: 8),
                  Text('ON CALL',
                      style: TextStyle(fontFamily: 'SpaceGrotesk', fontWeight: FontWeight.w700, fontSize: 14, color: AppColors.white, letterSpacing: 1.2)),
                ]),
                const SizedBox(height: 12),
                Text(
                  Fmt.timer(duration),
                  style: const TextStyle(
                    fontFamily: 'monospace', fontWeight: FontWeight.w700, fontSize: 48,
                    color: AppColors.white, letterSpacing: 2,
                  ),
                ),
                const SizedBox(height: 8),
                Text(lead.name, style: const TextStyle(fontFamily: 'SpaceGrotesk', fontWeight: FontWeight.w700, fontSize: 18, color: AppColors.white)),
                Text(Fmt.displayPhone(lead.phone),
                    style: TextStyle(fontFamily: 'monospace', fontSize: 13, color: AppColors.white.withOpacity(0.85))),
              ]),
            ),

            const SizedBox(height: 20),

            // Quick notes
            BrutalCard(
              padding: const EdgeInsets.all(12),
              color: AppColors.white,
              child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
                const Text('LIVE NOTES', style: AppTextStyles.label),
                const SizedBox(height: 8),
                TextField(
                  controller: _notesCtrl,
                  maxLines: 3,
                  minLines: 2,
                  onChanged: (v) => ref.read(dialerProvider.notifier).updateCallNotes(v),
                  style: const TextStyle(fontFamily: 'DMSans', fontSize: 14),
                  decoration: const InputDecoration(
                    hintText: 'Type notes during the call…',
                    hintStyle: TextStyle(fontFamily: 'DMSans', color: AppColors.grey, fontSize: 13),
                    border: InputBorder.none,
                    contentPadding: EdgeInsets.zero,
                  ),
                ),
              ]),
            ),

            const SizedBox(height: 14),

            // Action buttons (voice note, etc.)
            Row(children: [
              Expanded(
                child: BrutalButton(
                  label: _isRecordingNote ? 'STOP REC' : 'VOICE NOTE',
                  iconData: _isRecordingNote ? Icons.stop : Icons.mic,
                  backgroundColor: _isRecordingNote ? AppColors.error : AppColors.purple,
                  textColor: AppColors.white,
                  isFullWidth: true,
                  onPressed: _toggleRecording,
                ),
              ),
              const SizedBox(width: 10),
              Expanded(
                child: BrutalButton(
                  label: 'END CALL',
                  iconData: Icons.call_end,
                  backgroundColor: AppColors.error,
                  textColor: AppColors.white,
                  isFullWidth: true,
                  onPressed: () {
                    HapticFeedback.heavyImpact();
                    ref.read(dialerProvider.notifier).markCallEnded(
                      durationSec: duration,
                      wasConnected: duration > 5,
                    );
                  },
                ),
              ),
            ]),

            if (_voiceNotePath != null)
              Padding(
                padding: const EdgeInsets.only(top: 8),
                child: Container(
                  padding: const EdgeInsets.all(8),
                  decoration: BoxDecoration(
                    color: AppColors.successBg,
                    border: Border.all(color: AppColors.success, width: 1.5),
                  ),
                  child: const Row(children: [
                    Icon(Icons.check_circle, size: 14, color: AppColors.success),
                    SizedBox(width: 6),
                    Text('Voice note recorded', style: TextStyle(fontFamily: 'DMSans', fontSize: 11, color: AppColors.success)),
                  ]),
                ),
              ),
          ]),
        );
      },
    );
  }
}

// ─── DISPOSITION VIEW (MANDATORY) ───────────────────────────
final _dispositionsProvider = FutureProvider<List<CallDisposition>>(
  (_) => CallsService.instance.getDispositions(),
);

class _DispositionView extends ConsumerStatefulWidget {
  final DialerState state;
  const _DispositionView({required this.state});

  @override
  ConsumerState<_DispositionView> createState() => _DispositionViewState();
}

class _DispositionViewState extends ConsumerState<_DispositionView> {
  CallDisposition? _selected;
  final _notesCtrl = TextEditingController();
  bool _scheduleFollowup = false;
  DateTime? _followupDate;
  bool _saving = false;
  late bool _wasConnected;

  @override
  void initState() {
    super.initState();
    _wasConnected = widget.state.currentCall?.wasConnected ?? false;
    _notesCtrl.text = widget.state.currentCall?.notes ?? '';
  }

  @override
  void dispose() {
    _notesCtrl.dispose();
    super.dispose();
  }

  Future<void> _save() async {
    if (_selected == null) {
      AppToast.show(context, 'Select a disposition', isError: true);
      return;
    }
    setState(() => _saving = true);

    // Upload voice note if any
    String? recordingUrl;
    final voicePath = VoiceRecorderService.instance.currentPath;
    if (voicePath != null && !VoiceRecorderService.instance.isRecording) {
      try {
        recordingUrl = await VoiceRecorderService.instance.uploadToCloudinary(voicePath);
      } catch (_) {}
    }

    // Save disposition + call to backend
    await ref.read(dialerProvider.notifier).dispose_(
      dispositionId: _selected!.id,
      dispositionName: _selected!.name,
      notes: _notesCtrl.text,
      wasConnected: _wasConnected,
      recordingUrl: recordingUrl,
    );

    // Schedule auto-followup if disposition requires it or user opted in
    if (_scheduleFollowup && _followupDate != null) {
      try {
        await LeadsService.instance.createFollowup(
          widget.state.currentCall!.leadId,
          {
            'followup_type': 'call',
            'scheduled_at': _followupDate!.toUtc().toIso8601String(),
            'notes': _notesCtrl.text,
            'assigned_to': 0,
          },
        );
      } catch (_) {}
    } else if (_selected!.autoFollowupHours != null && _selected!.autoFollowupHours! > 0) {
      try {
        final auto = DateTime.now().add(Duration(hours: _selected!.autoFollowupHours!));
        await LeadsService.instance.createFollowup(
          widget.state.currentCall!.leadId,
          {
            'followup_type': 'call',
            'scheduled_at': auto.toUtc().toIso8601String(),
            'notes': 'Auto-scheduled from ${_selected!.name} disposition',
            'assigned_to': 0,
          },
        );
      } catch (_) {}
    }

    if (mounted) {
      setState(() => _saving = false);
      AppToast.show(context, 'Call disposed', isSuccess: true);
    }
  }

  @override
  Widget build(BuildContext context) {
    final lead = widget.state.currentLead;
    final call = widget.state.currentCall;
    if (lead == null || call == null) return const SizedBox.shrink();
    final dispositionsAsync = ref.watch(_dispositionsProvider);

    return SingleChildScrollView(
      padding: const EdgeInsets.all(16),
      child: Column(crossAxisAlignment: CrossAxisAlignment.stretch, children: [
        // Mandatory banner
        Container(
          padding: const EdgeInsets.all(12),
          decoration: BoxDecoration(
            color: AppColors.warningBg,
            border: Border.all(color: AppColors.warning, width: 2),
            boxShadow: const [BoxShadow(color: AppColors.black, offset: Offset(3, 3))],
          ),
          child: Row(children: const [
            Icon(Icons.warning_amber_rounded, color: AppColors.warning, size: 22),
            SizedBox(width: 10),
            Expanded(child: Text(
              'Disposition required before next call',
              style: TextStyle(fontFamily: 'SpaceGrotesk', fontWeight: FontWeight.w700, fontSize: 13, color: Color(0xFF854D0E)),
            )),
          ]),
        ),

        const SizedBox(height: 14),

        // Call summary
        BrutalCard(
          padding: const EdgeInsets.all(14),
          color: AppColors.dark,
          child: Row(children: [
            Container(
              width: 50, height: 50,
              decoration: BoxDecoration(
                color: AppColors.yellow,
                border: Border.all(color: AppColors.black, width: 1.5),
              ),
              child: const Icon(Icons.call_end, color: AppColors.black, size: 24),
            ),
            const SizedBox(width: 12),
            Expanded(child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
              Text(lead.name, style: const TextStyle(fontFamily: 'SpaceGrotesk', fontWeight: FontWeight.w700, fontSize: 16, color: AppColors.white)),
              const SizedBox(height: 2),
              Row(children: [
                Text(
                  Fmt.duration(call.durationSec),
                  style: const TextStyle(fontFamily: 'monospace', fontWeight: FontWeight.w700, fontSize: 14, color: AppColors.yellow),
                ),
                const SizedBox(width: 10),
                if (_wasConnected)
                  const TagChip(label: '✓ Connected', backgroundColor: AppColors.success, textColor: AppColors.white)
                else
                  const TagChip(label: '✕ No Answer', backgroundColor: AppColors.greyLight),
              ]),
            ])),
          ]),
        ),

        const SizedBox(height: 16),

        // Was connected toggle
        BrutalCard(
          padding: const EdgeInsets.all(10),
          child: Row(children: [
            const Expanded(child: Text('Was the call connected?', style: AppTextStyles.bodyMedium)),
            Switch(
              value: _wasConnected,
              onChanged: (v) => setState(() => _wasConnected = v),
              activeColor: AppColors.success,
              activeTrackColor: AppColors.successBg,
              inactiveThumbColor: AppColors.grey,
              inactiveTrackColor: AppColors.greyLight,
            ),
          ]),
        ),

        const SizedBox(height: 16),

        // Disposition selection
        const Text('SELECT DISPOSITION *', style: AppTextStyles.label),
        const SizedBox(height: 8),

        dispositionsAsync.when(
          loading: () => const Center(child: CircularProgressIndicator()),
          error: (_, __) => const Text('Failed to load dispositions'),
          data: (dispositions) {
            if (dispositions.isEmpty) {
              return const Padding(
                padding: EdgeInsets.all(16),
                child: Text(
                  'No dispositions configured. Ask admin to seed them.',
                  textAlign: TextAlign.center,
                  style: TextStyle(fontFamily: 'DMSans', fontSize: 12, color: AppColors.grey),
                ),
              );
            }
            return Wrap(spacing: 8, runSpacing: 8, children: dispositions.map((d) {
              final selected = _selected?.id == d.id;
              return GestureDetector(
                onTap: () { HapticFeedback.selectionClick(); setState(() => _selected = d); },
                child: AnimatedContainer(
                  duration: const Duration(milliseconds: 100),
                  padding: const EdgeInsets.symmetric(horizontal: 12, vertical: 8),
                  decoration: BoxDecoration(
                    color: selected
                        ? (d.isPositive ? AppColors.success : AppColors.error)
                        : AppColors.white,
                    border: Border.all(color: AppColors.black, width: 2),
                    boxShadow: selected
                        ? const [BoxShadow(color: AppColors.black, offset: Offset(2, 2))]
                        : const [BoxShadow(color: AppColors.black, offset: Offset(3, 3))],
                  ),
                  child: Row(mainAxisSize: MainAxisSize.min, children: [
                    Icon(
                      d.isPositive ? Icons.thumb_up : Icons.thumb_down,
                      size: 12,
                      color: selected ? AppColors.white : (d.isPositive ? AppColors.success : AppColors.error),
                    ),
                    const SizedBox(width: 6),
                    Text(
                      d.name,
                      style: TextStyle(
                        fontFamily: 'SpaceGrotesk', fontWeight: FontWeight.w700, fontSize: 12,
                        color: selected ? AppColors.white : AppColors.black,
                      ),
                    ),
                  ]),
                ),
              );
            }).toList());
          },
        ),

        const SizedBox(height: 16),

        // Notes
        BrutalTextField(
          label: 'Call Notes',
          hint: 'What did the lead say? Outcome details…',
          controller: _notesCtrl,
          maxLines: 4, minLines: 3,
        ),

        const SizedBox(height: 14),

        // Schedule follow-up
        BrutalCard(
          padding: const EdgeInsets.all(12),
          color: _scheduleFollowup ? AppColors.warningBg : AppColors.white,
          child: Column(children: [
            Row(children: [
              const Expanded(child: Text('📅 Schedule a follow-up call', style: AppTextStyles.bodyBold)),
              Switch(
                value: _scheduleFollowup,
                onChanged: (v) => setState(() => _scheduleFollowup = v),
                activeColor: AppColors.warning,
              ),
            ]),
            if (_scheduleFollowup) ...[
              const SizedBox(height: 8),
              Row(children: [
                Expanded(child: BrutalButton.secondary(
                  label: '+1 hour',
                  isFullWidth: true,
                  onPressed: () => setState(() => _followupDate = DateTime.now().add(const Duration(hours: 1))),
                )),
                const SizedBox(width: 6),
                Expanded(child: BrutalButton.secondary(
                  label: 'Tomorrow',
                  isFullWidth: true,
                  onPressed: () => setState(() => _followupDate = DateTime.now().add(const Duration(days: 1))),
                )),
                const SizedBox(width: 6),
                Expanded(child: BrutalButton.secondary(
                  label: 'Pick',
                  isFullWidth: true,
                  onPressed: () async {
                    final date = await showDatePicker(
                      context: context,
                      initialDate: DateTime.now().add(const Duration(days: 1)),
                      firstDate: DateTime.now(),
                      lastDate: DateTime.now().add(const Duration(days: 365)),
                    );
                    if (date != null && mounted) {
                      final time = await showTimePicker(
                        context: context,
                        initialTime: const TimeOfDay(hour: 10, minute: 0),
                      );
                      if (time != null) {
                        setState(() => _followupDate = DateTime(date.year, date.month, date.day, time.hour, time.minute));
                      }
                    }
                  },
                )),
              ]),
              if (_followupDate != null)
                Padding(
                  padding: const EdgeInsets.only(top: 8),
                  child: Row(children: [
                    const Icon(Icons.event, size: 13, color: AppColors.warning),
                    const SizedBox(width: 4),
                    Text(
                      Fmt.dateTime(_followupDate!.toIso8601String()),
                      style: const TextStyle(fontFamily: 'SpaceGrotesk', fontWeight: FontWeight.w700, fontSize: 12, color: AppColors.warning),
                    ),
                  ]),
                ),
            ],
          ]),
        ),

        const SizedBox(height: 20),

        BrutalButton(
          label: widget.state.mode == DialerMode.queue ? 'SAVE & NEXT →' : 'SAVE DISPOSITION',
          iconData: Icons.check,
          backgroundColor: AppColors.black,
          textColor: AppColors.white,
          isFullWidth: true,
          shadowOffset: 5,
          isLoading: _saving,
          onPressed: _saving ? null : _save,
        ),
      ]),
    );
  }
}

// ─── PAUSED VIEW ────────────────────────────────────────────
class _PausedView extends ConsumerWidget {
  final DialerState state;
  const _PausedView({required this.state});

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    return Center(
      child: Padding(
        padding: const EdgeInsets.all(32),
        child: Column(mainAxisSize: MainAxisSize.min, children: [
          Container(
            padding: const EdgeInsets.all(20),
            decoration: BoxDecoration(
              color: AppColors.warningBg,
              border: Border.all(color: AppColors.warning, width: 2),
              boxShadow: const [BoxShadow(color: AppColors.black, offset: Offset(4, 4))],
            ),
            child: const Icon(Icons.pause_circle, size: 48, color: AppColors.warning),
          ),
          const SizedBox(height: 16),
          const Text('PAUSED', style: AppTextStyles.h1),
          const SizedBox(height: 4),
          Text(
            '${state.callsDone} of ${state.totalCalls} calls completed',
            style: AppTextStyles.body.copyWith(color: AppColors.grey),
          ),
          const SizedBox(height: 28),
          BrutalButton(
            label: 'RESUME QUEUE',
            iconData: Icons.play_arrow,
            backgroundColor: AppColors.success,
            textColor: AppColors.white,
            isFullWidth: false,
            onPressed: () => ref.read(dialerProvider.notifier).resume(),
          ),
        ]),
      ),
    );
  }
}

// ─── COMPLETED VIEW ─────────────────────────────────────────
class _CompletedView extends ConsumerWidget {
  final DialerState state;
  const _CompletedView({required this.state});

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final connected = state.completedCalls.where((c) => c.wasConnected).length;
    final connRate = state.completedCalls.isEmpty ? 0 : ((connected / state.completedCalls.length) * 100).round();

    return SingleChildScrollView(
      padding: const EdgeInsets.all(20),
      child: Column(children: [
        const SizedBox(height: 20),
        Container(
          padding: const EdgeInsets.all(24),
          decoration: BoxDecoration(
            gradient: AppColors.successGradient,
            border: Border.all(color: AppColors.black, width: 2.5),
            boxShadow: const [BoxShadow(color: AppColors.black, offset: Offset(6, 6))],
          ),
          child: Column(children: const [
            Icon(Icons.check_circle, size: 60, color: AppColors.white),
            SizedBox(height: 12),
            Text(
              'QUEUE COMPLETE',
              style: TextStyle(fontFamily: 'SpaceGrotesk', fontWeight: FontWeight.w700, fontSize: 22, color: AppColors.white, letterSpacing: 0.5),
            ),
          ]),
        ).animate().scale(begin: const Offset(0.7, 0.7), curve: Curves.easeOutBack),

        const SizedBox(height: 24),
        // Summary stats
        Row(children: [
          Expanded(child: StatCard(
            label: 'Total Calls', value: '${state.completedCalls.length}', icon: Icons.call,
            accentColor: AppColors.info,
          )),
          const SizedBox(width: 10),
          Expanded(child: StatCard(
            label: 'Connected', value: '$connected', icon: Icons.check,
            accentColor: AppColors.success,
          )),
        ]),
        const SizedBox(height: 10),
        Row(children: [
          Expanded(child: StatCard(
            label: 'Connect Rate', value: '$connRate%', icon: Icons.percent,
            accentColor: AppColors.warning,
          )),
          const SizedBox(width: 10),
          Expanded(child: StatCard(
            label: 'Total Time',
            value: Fmt.duration(state.completedCalls.fold(0, (s, c) => s + c.durationSec)),
            icon: Icons.timer, accentColor: AppColors.purple,
          )),
        ]),
        const SizedBox(height: 24),
        BrutalButton.primary(
          label: 'DONE',
          isFullWidth: true,
          onPressed: () {
            ref.read(dialerProvider.notifier).stop();
            context.pop();
          },
        ),
      ]),
    );
  }
}
