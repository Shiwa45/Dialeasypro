// ─────────────────────────────────────────────────────────────
// AI insight for a single call, shown as a bottom sheet from the call log.
//
// Agent-facing view: what the AI heard, what to do next, and the coaching
// note. Deliberately no re-analyse button — that costs tokens and belongs to
// the manager in the web admin, and the backend rejects it from an agent's
// token anyway.
// ─────────────────────────────────────────────────────────────
import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';

import '../../core/theme/colors.dart';
import '../../core/utils/utils.dart';
import '../../core/widgets/widgets.dart';
import '../../data/models/addon_models.dart';
import '../../data/services/addon_services.dart';

/// (insight, transcript) for one call. Both may be absent while the pipeline
/// is still running, which is the normal state right after a call ends.
final _insightProvider =
    FutureProvider.autoDispose.family<(CallInsight?, CallTranscript?), String>((ref, callId) async {
  final insight = await AiService.instance.insight(callId);
  CallTranscript? transcript;
  try {
    transcript = await AiService.instance.transcript(callId);
  } catch (_) {
    // 404 when the call has no recording at all — not an error worth showing.
  }
  return (insight, transcript);
});

const _sentimentStyles = {
  'positive': (Icons.trending_up, AppColors.success, AppColors.successBg),
  'neutral': (Icons.trending_flat, AppColors.grey, AppColors.greyLight),
  'negative': (Icons.trending_down, AppColors.error, AppColors.errorBg),
};

void showCallInsightSheet(BuildContext context, String callId) {
  showModalBottomSheet(
    context: context,
    isScrollControlled: true,
    backgroundColor: Colors.transparent,
    builder: (_) => DraggableScrollableSheet(
      initialChildSize: 0.75,
      minChildSize: 0.4,
      maxChildSize: 0.95,
      expand: false,
      builder: (_, controller) => Container(
        decoration: const BoxDecoration(
          color: AppColors.background,
          border: Border(top: BorderSide(color: AppColors.black, width: 2)),
        ),
        child: _CallInsightBody(callId: callId, controller: controller),
      ),
    ),
  );
}

class _CallInsightBody extends ConsumerWidget {
  final String callId;
  final ScrollController controller;
  const _CallInsightBody({required this.callId, required this.controller});

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final async = ref.watch(_insightProvider(callId));

    return Column(children: [
      // Grab handle
      Container(
        margin: const EdgeInsets.symmetric(vertical: 10),
        width: 40, height: 4,
        decoration: BoxDecoration(color: AppColors.grey, borderRadius: BorderRadius.circular(2)),
      ),
      Expanded(
        child: async.when(
          loading: () => const Center(child: CircularProgressIndicator(color: AppColors.black)),
          error: (e, __) => const EmptyStateView(
            icon: Icons.cloud_off,
            title: 'Could not load',
            message: 'Check your connection and try again.',
          ),
          data: (data) {
            final (insight, transcript) = data;
            if (insight == null || !insight.isReady) {
              return _pending(transcript);
            }
            return _insight(context, insight, transcript);
          },
        ),
      ),
    ]);
  }

  /// The pipeline runs after upload, so "not ready" is the common case for a
  /// call that just ended. Say which stage it's at rather than "no data".
  Widget _pending(CallTranscript? transcript) {
    if (transcript == null) {
      return const EmptyStateView(
        icon: Icons.mic_off,
        title: 'No recording',
        message: 'This call has no recording, so there is nothing to analyse.',
      );
    }
    return switch (transcript.status) {
      'failed' => EmptyStateView(
          icon: Icons.error_outline,
          title: 'Transcription failed',
          message: transcript.transcript.isEmpty
              ? 'The recording could not be transcribed. Ask your manager to retry it.'
              : transcript.transcript,
        ),
      'done' => const EmptyStateView(
          icon: Icons.hourglass_empty,
          title: 'Analysing',
          message: 'The transcript is ready. Insights usually appear within a minute.',
        ),
      _ => const EmptyStateView(
          icon: Icons.hourglass_empty,
          title: 'Transcribing',
          message: 'This call is being transcribed. Check back in a minute.',
        ),
    };
  }

  Widget _insight(BuildContext context, CallInsight i, CallTranscript? transcript) {
    final (icon, fg, bg) = _sentimentStyles[i.sentiment] ??
        (Icons.trending_flat, AppColors.grey, AppColors.greyLight);

    return ListView(
      controller: controller,
      padding: const EdgeInsets.fromLTRB(16, 4, 16, 32),
      children: [
        Row(children: [
          Container(
            padding: const EdgeInsets.symmetric(horizontal: 10, vertical: 5),
            decoration: BoxDecoration(color: bg, border: Border.all(color: AppColors.black, width: 2)),
            child: Row(mainAxisSize: MainAxisSize.min, children: [
              Icon(icon, size: 15, color: fg),
              const SizedBox(width: 6),
              Text(i.sentiment.toUpperCase(),
                  style: AppTextStyles.h5.copyWith(fontSize: 11, color: fg)),
            ]),
          ),
          const Spacer(),
          if (i.generatedAt != null)
            Text(Fmt.relative(i.generatedAt!.toIso8601String()), style: AppTextStyles.caption),
        ]),
        const SizedBox(height: 14),

        Text(i.summary, style: AppTextStyles.body),

        if (i.nextAction.isNotEmpty) ...[
          const SizedBox(height: 18),
          BrutalCard(
            color: AppColors.yellow,
            padding: const EdgeInsets.all(14),
            child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
              Text('DO THIS NEXT', style: AppTextStyles.h5.copyWith(fontSize: 10, letterSpacing: 1)),
              const SizedBox(height: 4),
              Text(i.nextAction, style: AppTextStyles.body),
            ]),
          ),
        ],

        _bullets('Key points', i.keyPoints),
        _bullets('Objections raised', i.objections),

        if (i.suggestedDispositionName != null) ...[
          const SizedBox(height: 18),
          InfoRow(label: 'Suggested outcome', value: i.suggestedDispositionName!),
        ],

        if (i.coachingNotes.isNotEmpty) ...[
          const SizedBox(height: 18),
          const SectionHeader(title: 'Coaching'),
          const SizedBox(height: 6),
          Text(i.coachingNotes, style: AppTextStyles.body),
        ],

        if (transcript != null && transcript.isReady) ...[
          const SizedBox(height: 18),
          _TranscriptTile(text: transcript.transcript),
        ],
      ],
    );
  }

  Widget _bullets(String title, List<String> items) {
    if (items.isEmpty) return const SizedBox.shrink();
    return Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
      const SizedBox(height: 18),
      SectionHeader(title: title),
      const SizedBox(height: 6),
      ...items.map((t) => Padding(
            padding: const EdgeInsets.only(bottom: 6),
            child: Row(crossAxisAlignment: CrossAxisAlignment.start, children: [
              const Text('• ', style: TextStyle(fontWeight: FontWeight.bold)),
              Expanded(child: Text(t, style: AppTextStyles.body)),
            ]),
          )),
    ]);
  }
}

class _TranscriptTile extends StatelessWidget {
  final String text;
  const _TranscriptTile({required this.text});

  @override
  Widget build(BuildContext context) {
    return BrutalCard(
      padding: EdgeInsets.zero,
      child: Theme(
        data: Theme.of(context).copyWith(dividerColor: Colors.transparent),
        child: ExpansionTile(
          tilePadding: const EdgeInsets.symmetric(horizontal: 14),
          title: Text('Full transcript', style: AppTextStyles.h5),
          children: [
            Padding(
              padding: const EdgeInsets.fromLTRB(14, 0, 14, 14),
              child: SelectableText(text, style: AppTextStyles.caption.copyWith(height: 1.6)),
            ),
          ],
        ),
      ),
    );
  }
}
