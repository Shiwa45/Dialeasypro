import 'package:flutter/material.dart';
import 'package:flutter/services.dart';
import '../../core/theme/colors.dart';
import '../../core/utils/utils.dart';
import '../../core/widgets/widgets.dart';
import '../../data/models/models.dart';
import '../../data/services/api_client.dart';
import '../../data/services/services.dart';
import 'answered_toggle.dart';

// ============================================================
// DialSathi — Set the outcome of a call saved without one
//
// A click-to-call or a provider call is saved before anyone knows how it
// went, and there was no way to add the outcome afterwards — those calls
// stayed outcome-less in every report. Same rule as the post-call screen:
// first "was it answered?", then only the outcomes for that answer.
// ============================================================

/// Returns the updated call, or null when the agent closed the sheet.
Future<CallLog?> showCallOutcomeSheet(BuildContext context, CallLog call) {
  return showModalBottomSheet<CallLog>(
    context: context,
    isScrollControlled: true,
    backgroundColor: AppColors.background,
    builder: (ctx) => Padding(
      padding: EdgeInsets.only(bottom: MediaQuery.of(ctx).viewInsets.bottom),
      child: _CallOutcomeBody(call: call),
    ),
  );
}

class _CallOutcomeBody extends StatefulWidget {
  final CallLog call;
  const _CallOutcomeBody({required this.call});

  @override
  State<_CallOutcomeBody> createState() => _CallOutcomeBodyState();
}

class _CallOutcomeBodyState extends State<_CallOutcomeBody> {
  late Future<List<CallDisposition>> _dispositions;
  bool? _answered;
  CallDisposition? _selected;
  final _talkCtrl = TextEditingController();
  final _notesCtrl = TextEditingController();
  bool _saving = false;

  @override
  void initState() {
    super.initState();
    _dispositions = CallsService.instance.getDispositionsResilient();
    // A provider that reported talk time has already answered the question.
    if (widget.call.durationSeconds > 0) {
      _answered = true;
      _talkCtrl.text = '${widget.call.durationSeconds}';
    }
  }

  @override
  void dispose() {
    _talkCtrl.dispose();
    _notesCtrl.dispose();
    super.dispose();
  }

  void _setAnswered(bool v) {
    if (_answered == v) return;
    HapticFeedback.selectionClick();
    setState(() {
      _answered = v;
      if (_selected != null && _selected!.isConnectedOutcome != v) _selected = null;
    });
  }

  Future<void> _save() async {
    if (_answered == null || _selected == null) return;
    final talk = int.tryParse(_talkCtrl.text.trim());
    setState(() => _saving = true);
    try {
      final updated = await CallsService.instance.setOutcome(
        widget.call.id,
        disposition: _selected!.id,
        connected: _answered!,
        durationSeconds: _answered! && talk != null && talk > 0 ? talk : null,
        notes: _notesCtrl.text,
      );
      if (mounted) {
        AppToast.show(context, 'Outcome saved', isSuccess: true);
        Navigator.pop(context, updated);
      }
    } catch (e) {
      if (mounted) {
        setState(() => _saving = false);
        AppToast.show(context, ApiClient.errorMessage(e), isError: true);
      }
    }
  }

  @override
  Widget build(BuildContext context) {
    final c = widget.call;
    return SafeArea(
      child: SingleChildScrollView(
        padding: const EdgeInsets.fromLTRB(16, 16, 16, 20),
        child: Column(crossAxisAlignment: CrossAxisAlignment.stretch, children: [
          const Text('SET CALL OUTCOME', style: AppTextStyles.label),
          const SizedBox(height: 4),
          Text('${c.leadName ?? Fmt.displayPhone(c.phoneNumber)} · ${Fmt.relative(c.startedAt)}',
              style: AppTextStyles.caption),
          const SizedBox(height: 14),
          const Text('Was the call answered? *', style: AppTextStyles.bodyMedium),
          const SizedBox(height: 8),
          AnsweredToggle(value: _answered, onChanged: _setAnswered),
          const SizedBox(height: 14),
          if (_answered != null)
            FutureBuilder<List<CallDisposition>>(
              future: _dispositions,
              builder: (context, snap) {
                if (snap.connectionState != ConnectionState.done) {
                  return const Center(child: Padding(padding: EdgeInsets.all(12), child: CircularProgressIndicator()));
                }
                if (snap.hasError) {
                  return Text('Could not load call outcomes: ${ApiClient.errorMessage(snap.error)}',
                      style: const TextStyle(fontSize: 12, color: AppColors.error));
                }
                final options = (snap.data ?? const <CallDisposition>[])
                    .where((d) => d.isConnectedOutcome == _answered)
                    .toList();
                return DropdownButtonFormField<int>(
                  key: ValueKey('$_answered-${options.map((d) => d.id).join(',')}'),
                  initialValue: options.any((d) => d.id == _selected?.id) ? _selected!.id : null,
                  isExpanded: true,
                  hint: const Text('Choose the call outcome'),
                  decoration: InputDecoration(helperText: _selected?.effectLine),
                  items: [
                    for (final d in options)
                      DropdownMenuItem<int>(value: d.id, child: Text(d.name, overflow: TextOverflow.ellipsis)),
                  ],
                  onChanged: (id) => setState(() => _selected = options.firstWhere((d) => d.id == id)),
                );
              },
            ),
          if (_answered == true) ...[
            const SizedBox(height: 12),
            BrutalTextField(
              label: 'Talk time (seconds)',
              hint: 'e.g. 120',
              controller: _talkCtrl,
              keyboardType: TextInputType.number,
            ),
          ],
          const SizedBox(height: 12),
          BrutalTextField(label: 'Notes', controller: _notesCtrl, maxLines: 3, minLines: 2),
          const SizedBox(height: 16),
          BrutalButton.primary(
            label: 'SAVE OUTCOME',
            isLoading: _saving,
            onPressed: _answered == null || _selected == null || _saving ? null : _save,
          ),
        ]),
      ),
    );
  }
}
