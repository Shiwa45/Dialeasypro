import 'dart:async';
import 'dart:convert';

import 'package:dio/dio.dart';
import 'package:flutter/material.dart';
import 'package:flutter_animate/flutter_animate.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:go_router/go_router.dart';
import '../../core/theme/colors.dart';
import '../../core/utils/utils.dart';
import '../../core/widgets/widgets.dart';
import '../../data/services/api_client.dart';
import '../auth/auth_provider.dart';

// ============================================================
// DialSathi — Quick lead import (managers and admins)
//
// Paste comma-separated rows; they are sent as a CSV file to the same import
// the web uses, so every import gets a batch, the duplicate rule, row-level
// results and a place in the import history.
//
// This used to create leads one request at a time from the phone: no batch,
// no import record, no reason for any failure, silently skipped lines — and
// it was open to every agent, although bulk import is manager-only on the web.
// ============================================================

/// One pasted line, parsed.
class ImportRow {
  final String name, phone, email, city, requirement;
  const ImportRow({required this.name, required this.phone, this.email = '', this.city = '', this.requirement = ''});
}

/// Parse pasted lines: `name, phone[, email[, city[, requirement…]]]`.
/// Returns the rows and the 1-based line numbers that could not be used —
/// they used to be dropped without a word.
({List<ImportRow> rows, List<int> skipped}) parseImportText(String text) {
  final rows = <ImportRow>[];
  final skipped = <int>[];
  final lines = text.split('\n');
  for (var i = 0; i < lines.length; i++) {
    final line = lines[i];
    if (line.trim().isEmpty) continue;
    final cols = line.split(',').map((c) => c.trim()).toList();
    final digits = cols.length > 1 ? cols[1].replaceAll(RegExp(r'[^\d]'), '') : '';
    if (cols.length < 2 || cols[0].isEmpty || digits.length < 10) {
      skipped.add(i + 1);
      continue;
    }
    rows.add(ImportRow(
      name: cols[0],
      phone: cols[1],
      email: cols.length > 2 ? cols[2] : '',
      city: cols.length > 3 ? cols[3] : '',
      requirement: cols.length > 4 ? cols.sublist(4).join(', ').trim() : '',
    ));
  }
  return (rows: rows, skipped: skipped);
}

/// The rows as a CSV file with a header, quoting where needed.
String buildImportCsv(List<ImportRow> rows) {
  String cell(String v) =>
      (v.contains(',') || v.contains('"') || v.contains('\n')) ? '"${v.replaceAll('"', '""')}"' : v;
  final out = StringBuffer('name,phone,email,city,requirement\n');
  for (final r in rows) {
    out.writeln([r.name, r.phone, r.email, r.city, r.requirement].map(cell).join(','));
  }
  return out.toString();
}

class LeadImportScreen extends ConsumerStatefulWidget {
  const LeadImportScreen({super.key});

  @override
  ConsumerState<LeadImportScreen> createState() => _LeadImportScreenState();
}

class _LeadImportScreenState extends ConsumerState<LeadImportScreen> {
  final _csvCtrl = TextEditingController();
  final _batchCtrl = TextEditingController();
  String _source = 'manual';
  List<ImportRow> _rows = [];
  List<int> _skipped = [];
  bool _importing = false;
  Map<String, dynamic>? _result; // the finished import job

  @override
  void dispose() {
    _csvCtrl.dispose();
    _batchCtrl.dispose();
    super.dispose();
  }

  void _parse() {
    final parsed = parseImportText(_csvCtrl.text);
    setState(() {
      _rows = parsed.rows;
      _skipped = parsed.skipped;
      _result = null;
    });
    AppToast.show(
      context,
      parsed.skipped.isEmpty
          ? 'Parsed ${parsed.rows.length} rows'
          : 'Parsed ${parsed.rows.length} rows · ${parsed.skipped.length} line(s) skipped',
      isSuccess: parsed.rows.isNotEmpty && parsed.skipped.isEmpty,
      isError: parsed.rows.isEmpty,
    );
  }

  Future<void> _import() async {
    final batch = _batchCtrl.text.trim();
    if (batch.isEmpty) {
      AppToast.show(context, 'Give this import a batch name', isError: true);
      return;
    }
    setState(() { _importing = true; _result = null; });
    try {
      final dio = ApiClient.instance.dio;
      final start = await dio.post('/leads/import/', data: FormData.fromMap({
        'file': MultipartFile.fromBytes(utf8.encode(buildImportCsv(_rows)), filename: 'mobile_import.csv'),
        'batch_name': batch,
        'source': _source,
        'duplicate_action': 'skip',
        'column_mapping': jsonEncode({
          'name': 'name', 'phone': 'phone', 'email': 'email', 'city': 'city', 'requirement': 'requirement',
        }),
      }));
      final jobId = (start.data as Map)['import_job_id'] as String;

      // The import runs on the server; follow it until it finishes.
      Map<String, dynamic>? job;
      for (var i = 0; i < 60 && mounted; i++) {
        await Future<void>.delayed(const Duration(seconds: 2));
        job = ((await dio.get('/leads/import/$jobId/')).data as Map).cast<String, dynamic>();
        if (job['status'] == 'completed' || job['status'] == 'failed') break;
      }
      if (!mounted) return;
      setState(() { _importing = false; _result = job; });
    } catch (e) {
      if (!mounted) return;
      setState(() => _importing = false);
      AppToast.show(context, ApiClient.errorMessage(e), isError: true);
    }
  }

  @override
  Widget build(BuildContext context) {
    final role = ref.watch(currentAgentProvider)?.role ?? '';
    final allowed = role == 'admin' || role == 'manager';

    return Scaffold(
      backgroundColor: AppColors.background,
      appBar: AppBar(
        title: const Text('Import Leads'),
        leading: IconButton(icon: const Icon(Icons.arrow_back, color: AppColors.black), onPressed: () => context.pop()),
      ),
      body: !allowed
          ? const EmptyStateView(
              icon: Icons.lock_outline,
              title: 'Managers only',
              message: 'Bulk import is for managers and admins. Add leads one at a time with New Lead.',
            )
          : SingleChildScrollView(
              padding: const EdgeInsets.all(16),
              child: Column(crossAxisAlignment: CrossAxisAlignment.stretch, children: [
                Container(
                  padding: const EdgeInsets.all(12),
                  decoration: BoxDecoration(
                    color: AppColors.warningBg,
                    border: Border.all(color: AppColors.warning, width: 1),
                  ),
                  child: const Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
                    Row(children: [
                      Icon(Icons.info_outline, size: 16, color: AppColors.warning),
                      SizedBox(width: 6),
                      Text('CSV FORMAT', style: AppTextStyles.label),
                    ]),
                    SizedBox(height: 6),
                    Text(
                      'One lead per line. Columns:\nname, phone, email, city, requirement\n\n'
                      'Minimum: name and phone (10+ digits). Numbers already in the CRM are skipped.',
                      style: TextStyle(fontFamily: 'PlusJakartaSans', fontSize: 11, color: AppColors.dark, height: 1.5),
                    ),
                  ]),
                ).animate().fadeIn(),
                const SizedBox(height: 14),
                BrutalCard(padding: const EdgeInsets.all(14), child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
                  BrutalTextField(label: 'Batch name *', controller: _batchCtrl, hint: 'e.g. Diwali expo walk-ins'),
                  const SizedBox(height: 10),
                  _DropField(
                    label: 'Source',
                    value: _source,
                    options: Fmt.sourceLabels,
                    onChange: (v) => setState(() => _source = v),
                  ),
                ])),
                const SizedBox(height: 14),
                BrutalTextField(
                  label: 'Paste CSV Rows',
                  hint: 'Rahul Sharma, 9876543210, rahul@example.com, Mumbai, Wants demo\nPriya, 9123456789, priya@example.com',
                  controller: _csvCtrl,
                  maxLines: 8,
                  minLines: 5,
                ),
                const SizedBox(height: 12),
                Row(children: [
                  Expanded(child: BrutalButton.secondary(
                    label: 'PARSE',
                    iconData: Icons.search,
                    isFullWidth: true,
                    onPressed: _csvCtrl.text.isEmpty || _importing ? null : _parse,
                  )),
                  const SizedBox(width: 10),
                  Expanded(flex: 2, child: BrutalButton(
                    label: _importing ? 'Importing…' : 'IMPORT ${_rows.length} LEADS',
                    iconData: Icons.upload,
                    backgroundColor: AppColors.success,
                    textColor: AppColors.white,
                    isFullWidth: true,
                    isLoading: _importing,
                    onPressed: _rows.isEmpty || _importing ? null : _import,
                  )),
                ]),
                if (_skipped.isNotEmpty) ...[
                  const SizedBox(height: 10),
                  Text(
                    'Skipped line(s) ${_skipped.take(12).join(', ')}${_skipped.length > 12 ? '…' : ''}: '
                    'each needs a name and a phone number of 10+ digits.',
                    style: const TextStyle(fontFamily: 'PlusJakartaSans', fontSize: 11.5, color: AppColors.error),
                  ),
                ],
                if (_result != null) ...[
                  const SizedBox(height: 18),
                  _ResultCard(job: _result!, onView: () => context.go('/leads')),
                ],
                if (_rows.isNotEmpty) ...[
                  const SizedBox(height: 18),
                  Row(children: [
                    const SectionHeader(title: 'Preview', icon: Icons.preview),
                    const Spacer(),
                    TagChip(label: '${_rows.length} ROWS', backgroundColor: AppColors.success, textColor: AppColors.white),
                  ]),
                  const SizedBox(height: 8),
                  ..._rows.take(20).map((r) => Padding(padding: const EdgeInsets.only(bottom: 6),
                    child: BrutalCard(padding: const EdgeInsets.all(10), child: Row(children: [
                      BrutalAvatar(name: r.name, size: 32),
                      const SizedBox(width: 10),
                      Expanded(child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
                        Text(r.name, style: AppTextStyles.bodyBold),
                        Row(children: [
                          Text(Fmt.displayPhone(r.phone), style: AppTextStyles.mono),
                          if (r.city.isNotEmpty) Text(' · ${r.city}', style: AppTextStyles.caption),
                        ]),
                      ])),
                    ])),
                  )),
                  if (_rows.length > 20)
                    Padding(padding: const EdgeInsets.only(top: 6), child: Text(
                      'And ${_rows.length - 20} more…', style: AppTextStyles.caption, textAlign: TextAlign.center,
                    )),
                ],
                const SizedBox(height: 40),
              ]),
            ),
    );
  }
}

/// The finished import: created / duplicates skipped / failed, from the job.
class _ResultCard extends StatelessWidget {
  final Map<String, dynamic> job;
  final VoidCallback onView;
  const _ResultCard({required this.job, required this.onView});

  @override
  Widget build(BuildContext context) {
    final created = (job['successful_rows'] as num?)?.toInt() ?? 0;
    final duplicates = (job['duplicate_rows'] as num?)?.toInt() ?? 0;
    final failed = (job['failed_rows'] as num?)?.toInt() ?? 0;
    final done = job['status'] == 'completed';
    final ok = done && failed == 0;
    return BrutalCard(
      padding: const EdgeInsets.all(14),
      color: ok ? AppColors.successBg : AppColors.warningBg,
      borderColor: ok ? AppColors.success : AppColors.warning,
      child: Row(children: [
        Icon(ok ? Icons.check_circle : Icons.warning, color: ok ? AppColors.success : AppColors.warning),
        const SizedBox(width: 10),
        Expanded(child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
          Text(!done ? 'Still importing — check the web import history' : ok ? 'Import complete' : 'Imported with problems',
              style: AppTextStyles.h5),
          Text('Created $created · Already in CRM $duplicates · Failed $failed', style: AppTextStyles.caption),
          if ((job['batch_label'] as String?)?.isNotEmpty == true)
            Text('Batch: ${job['batch_label']}', style: AppTextStyles.caption),
        ])),
        if (created > 0)
          BrutalButton.secondary(
            label: 'View Leads',
            isFullWidth: false,
            padding: const EdgeInsets.symmetric(horizontal: 10, vertical: 8),
            onPressed: onView,
          ),
      ]),
    );
  }
}

class _DropField extends StatelessWidget {
  final String label, value;
  final Map<String, String> options;
  final ValueChanged<String> onChange;
  const _DropField({required this.label, required this.value, required this.options, required this.onChange});

  @override
  Widget build(BuildContext context) => Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
    Text(label.toUpperCase(), style: AppTextStyles.label),
    const SizedBox(height: 4),
    Container(
      decoration: BoxDecoration(
        color: AppColors.white,
        border: Border.all(color: AppColors.line, width: 1),
      ),
      padding: const EdgeInsets.symmetric(horizontal: 10),
      child: DropdownButtonHideUnderline(child: DropdownButton<String>(
        value: options.containsKey(value) ? value : options.keys.first,
        isExpanded: true,
        items: options.entries.map((e) => DropdownMenuItem(
          value: e.key,
          child: Text(e.value, style: const TextStyle(fontFamily: 'PlusJakartaSans', fontSize: 12)),
        )).toList(),
        onChanged: (v) { if (v != null) onChange(v); },
        icon: const Icon(Icons.arrow_drop_down, color: AppColors.black, size: 18),
      )),
    ),
  ]);
}
