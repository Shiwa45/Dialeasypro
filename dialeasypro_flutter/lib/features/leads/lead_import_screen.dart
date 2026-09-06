import 'package:flutter/material.dart';
import 'package:flutter_animate/flutter_animate.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:go_router/go_router.dart';
import '../../core/theme/colors.dart';
import '../../core/utils/utils.dart';
import '../../core/widgets/widgets.dart';
import '../../data/services/services.dart';

// ============================================================
// DialEasypro — Quick CSV/Bulk Lead Import
// Lightweight mobile importer: paste comma-separated rows, parse,
// preview, and bulk-create. For large imports, agents should use
// the admin web panel.
// ============================================================

class LeadImportScreen extends ConsumerStatefulWidget {
  const LeadImportScreen({super.key});

  @override
  ConsumerState<LeadImportScreen> createState() => _LeadImportScreenState();
}

class _LeadImportScreenState extends ConsumerState<LeadImportScreen> {
  final _csvCtrl = TextEditingController();
  String _source = 'manual';
  String _priority = Fmt.defaultPriority;
  List<_ParsedRow> _rows = [];
  bool _importing = false;
  int _imported = 0, _failed = 0;

  @override
  void dispose() {
    _csvCtrl.dispose();
    super.dispose();
  }

  void _parseCsv() {
    final lines = _csvCtrl.text.split('\n').where((l) => l.trim().isNotEmpty).toList();
    final parsed = <_ParsedRow>[];
    for (final line in lines) {
      // Support: name,phone[,email[,city[,requirement]]]
      final cols = line.split(',').map((c) => c.trim()).toList();
      if (cols.length < 2) continue;
      if (cols[1].replaceAll(RegExp(r'[^\d]'), '').length < 10) continue;
      parsed.add(_ParsedRow(
        name: cols[0],
        phone: cols[1],
        email: cols.length > 2 ? cols[2] : '',
        city: cols.length > 3 ? cols[3] : '',
        requirement: cols.length > 4 ? cols.sublist(4).join(',') : '',
      ));
    }
    setState(() => _rows = parsed);
    AppToast.show(context, 'Parsed ${parsed.length} valid rows',
        isSuccess: parsed.isNotEmpty, isError: parsed.isEmpty);
  }

  Future<void> _import() async {
    if (_rows.isEmpty) {
      AppToast.show(context, 'Parse rows first', isError: true);
      return;
    }
    setState(() { _importing = true; _imported = 0; _failed = 0; });
    for (final r in _rows) {
      try {
        await LeadsService.instance.createLead({
          'name': r.name,
          'phone': Fmt.normalizePhone(r.phone),
          if (r.email.isNotEmpty) 'email': r.email,
          if (r.city.isNotEmpty) 'city': r.city,
          if (r.requirement.isNotEmpty) 'requirement': r.requirement,
          'source': _source,
          'priority': _priority,
          'status': 'new',
        });
        setState(() => _imported++);
      } catch (_) {
        setState(() => _failed++);
      }
    }
    setState(() => _importing = false);
    if (mounted) {
      AppToast.show(context, 'Imported $_imported / ${_rows.length} leads',
          isSuccess: _failed == 0, isError: _failed > 0);
    }
  }

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      backgroundColor: AppColors.background,
      appBar: AppBar(
        title: const Text('Import Leads'),
        leading: IconButton(icon: const Icon(Icons.arrow_back, color: AppColors.black), onPressed: () => context.pop()),
      ),
      body: SingleChildScrollView(
        padding: const EdgeInsets.all(16),
        child: Column(crossAxisAlignment: CrossAxisAlignment.stretch, children: [
          // Format hint
          Container(
            padding: const EdgeInsets.all(12),
            decoration: BoxDecoration(
              color: AppColors.warningBg,
              border: Border.all(color: AppColors.warning, width: 2),
              boxShadow: const [BoxShadow(color: AppColors.black, offset: Offset(3, 3))],
            ),
            child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: const [
              Row(children: [
                Icon(Icons.info_outline, size: 16, color: AppColors.warning),
                SizedBox(width: 6),
                Text('CSV FORMAT', style: AppTextStyles.label),
              ]),
              SizedBox(height: 6),
              Text(
                'One lead per line. Columns:\nname, phone, email, city, requirement\n\nMinimum: name and phone. Phone must be 10+ digits.',
                style: TextStyle(fontFamily: 'monospace', fontSize: 11, color: AppColors.dark, height: 1.5),
              ),
            ]),
          ).animate().fadeIn(),

          const SizedBox(height: 14),

          // Defaults
          BrutalCard(padding: const EdgeInsets.all(14), child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
            const Text('DEFAULTS FOR ALL ROWS', style: AppTextStyles.label),
            const SizedBox(height: 8),
            Row(children: [
              Expanded(child: _DropField(
                label: 'Source',
                value: _source,
                options: Fmt.sourceLabels,
                onChange: (v) => setState(() => _source = v),
              )),
              const SizedBox(width: 10),
              Expanded(child: _DropField(
                label: 'Priority',
                value: _priority,
                options: Fmt.priorityLabels,
                onChange: (v) => setState(() => _priority = v),
              )),
            ]),
          ])).animate().fadeIn(delay: 80.ms),

          const SizedBox(height: 14),

          // CSV input
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
              onPressed: _csvCtrl.text.isEmpty ? null : _parseCsv,
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
                'And ${_rows.length - 20} more…',
                style: AppTextStyles.caption,
                textAlign: TextAlign.center,
              )),
          ],

          if (_imported > 0 || _failed > 0) ...[
            const SizedBox(height: 18),
            BrutalCard(
              padding: const EdgeInsets.all(14),
              color: _failed > 0 ? AppColors.warningBg : AppColors.successBg,
              borderColor: _failed > 0 ? AppColors.warning : AppColors.success,
              child: Row(children: [
                Icon(_failed > 0 ? Icons.warning : Icons.check_circle,
                    color: _failed > 0 ? AppColors.warning : AppColors.success),
                const SizedBox(width: 10),
                Expanded(child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
                  Text(_failed > 0 ? 'Partial Success' : 'Import Complete', style: AppTextStyles.h5),
                  Text('Created: $_imported · Failed: $_failed', style: AppTextStyles.caption),
                ])),
                if (_imported > 0)
                  BrutalButton.secondary(
                    label: 'View Leads',
                    isFullWidth: false,
                    padding: const EdgeInsets.symmetric(horizontal: 10, vertical: 8),
                    onPressed: () => context.go('/leads'),
                  ),
              ]),
            ),
          ],
          const SizedBox(height: 40),
        ]),
      ),
    );
  }
}

class _ParsedRow {
  final String name, phone, email, city, requirement;
  const _ParsedRow({required this.name, required this.phone, this.email = '', this.city = '', this.requirement = ''});
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
        border: Border.all(color: AppColors.black, width: 1.5),
      ),
      padding: const EdgeInsets.symmetric(horizontal: 10),
      child: DropdownButtonHideUnderline(child: DropdownButton<String>(
        value: options.containsKey(value) ? value : options.keys.first,
        isExpanded: true,
        items: options.entries.map((e) => DropdownMenuItem(
          value: e.key,
          child: Text(e.value, style: const TextStyle(fontFamily: 'DMSans', fontSize: 12)),
        )).toList(),
        onChanged: (v) { if (v != null) onChange(v); },
        icon: const Icon(Icons.arrow_drop_down, color: AppColors.black, size: 18),
      )),
    ),
  ]);
}
