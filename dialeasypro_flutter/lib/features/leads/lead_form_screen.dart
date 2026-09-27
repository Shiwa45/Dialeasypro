import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:go_router/go_router.dart';
import '../../core/theme/colors.dart';
import '../../core/utils/utils.dart';
import '../../core/widgets/widgets.dart';
import '../../data/models/models.dart';
import '../../data/services/api_client.dart';
import '../../data/services/services.dart';

class LeadFormScreen extends ConsumerStatefulWidget {
  final int? leadId;
  const LeadFormScreen({super.key, this.leadId});

  @override
  ConsumerState<LeadFormScreen> createState() => _LeadFormScreenState();
}

class _LeadFormScreenState extends ConsumerState<LeadFormScreen> {
  final _name = TextEditingController();
  final _phone = TextEditingController();
  final _altPhone = TextEditingController();
  final _email = TextEditingController();
  final _city = TextEditingController();
  final _state = TextEditingController();
  final _req = TextEditingController();
  final _budget = TextEditingController();
  final _deal = TextEditingController();
  String _source = 'manual';
  String _status = 'new';
  String _priority = Fmt.defaultPriority;
  bool _loading = false;
  bool _initial = false;

  /// This client's form: which money fields show, their labels, and the
  /// custom fields the platform set up for them.
  LeadFormConfig _config = const LeadFormConfig();
  final Map<String, TextEditingController> _customText = {};
  final Map<String, String?> _customChoice = {};
  Map<String, String> _existingCustom = const {};

  @override
  void initState() {
    super.initState();
    _loadConfig();
    if (widget.leadId != null) _load();
  }

  Future<void> _loadConfig() async {
    final config = await LeadsService.instance.getFormConfig();
    if (!mounted) return;
    setState(() {
      _config = config;
      for (final f in config.customFields) {
        final existing = _existingCustom[f.key] ?? '';
        if (_isChoice(f)) {
          _customChoice[f.key] = existing.isEmpty ? null : existing;
        } else {
          _customText.putIfAbsent(f.key, () => TextEditingController(text: existing));
        }
      }
    });
  }

  static bool _isChoice(LeadFormField f) => f.type == 'dropdown' || f.type == 'checkbox';

  Future<void> _load() async {
    setState(() => _initial = true);
    try {
      final l = await LeadsService.instance.getLead(widget.leadId!);
      _name.text = l.name; _phone.text = l.phone; _altPhone.text = l.alternatePhone;
      _email.text = l.email; _city.text = l.city; _state.text = l.state;
      _req.text = l.requirement; _budget.text = l.budget ?? ''; _deal.text = l.dealValue ?? '';
      _existingCustom = {for (final c in l.customFields) c.key: c.value};
      // The form config may have arrived first; fill what it already built.
      for (final e in _existingCustom.entries) {
        _customText[e.key]?.text = e.value;
        if (_customChoice.containsKey(e.key)) _customChoice[e.key] = e.value.isEmpty ? null : e.value;
      }
      setState(() { _source = l.source; _status = l.status; _priority = l.priority; _initial = false; });
    } catch (_) { setState(() => _initial = false); }
  }

  @override
  void dispose() {
    for (final c in [_name, _phone, _altPhone, _email, _city, _state, _req, _budget, _deal]) c.dispose();
    for (final c in _customText.values) c.dispose();
    super.dispose();
  }

  Future<void> _submit() async {
    if (_name.text.trim().isEmpty || _phone.text.trim().isEmpty) {
      AppToast.show(context, 'Name and phone required', isError: true);
      return;
    }
    final custom = <String, String>{};
    for (final f in _config.customFields) {
      final value = _isChoice(f)
          ? (_customChoice[f.key] ?? '')
          : (_customText[f.key]?.text.trim() ?? '');
      if (f.required && value.isEmpty) {
        AppToast.show(context, '${f.name} is required', isError: true);
        return;
      }
      // On edit, send blanks too so a cleared value is cleared on the server.
      if (value.isNotEmpty || widget.leadId != null) custom[f.key] = value;
    }
    setState(() => _loading = true);
    final data = {
      'name': _name.text.trim(),
      'phone': Fmt.normalizePhone(_phone.text.trim()),
      if (_altPhone.text.isNotEmpty) 'alternate_phone': Fmt.normalizePhone(_altPhone.text.trim()),
      if (_email.text.isNotEmpty) 'email': _email.text.trim().toLowerCase(),
      if (_city.text.isNotEmpty) 'city': _city.text.trim(),
      if (_state.text.isNotEmpty) 'state': _state.text.trim(),
      if (_req.text.isNotEmpty) 'requirement': _req.text.trim(),
      if (_config.budget.show && _budget.text.isNotEmpty) 'budget': _budget.text.trim(),
      if (_config.dealValue.show && _deal.text.isNotEmpty) 'deal_value': _deal.text.trim(),
      if (custom.isNotEmpty) 'custom_fields': custom,
      'source': _source, 'status': _status, 'priority': _priority,
    };
    try {
      final lead = widget.leadId != null
          ? await LeadsService.instance.updateLead(widget.leadId!, data)
          : await LeadsService.instance.createLead(data);
      if (mounted) {
        AppToast.show(context, widget.leadId != null ? 'Updated!' : 'Lead created!', isSuccess: true);
        context.go('/leads/${lead.id}');
      }
    } catch (e) {
      setState(() => _loading = false);
      // Show what the server actually objected to. A bare "Failed" here hid an
      // invalid-choice rejection on every single submit.
      if (mounted) {
        AppToast.show(context, ApiClient.errorMessage(e), isError: true);
      }
    }
  }

  /// One custom field as the right input for its type.
  Widget _customInput(LeadFormField f) {
    final label = f.required ? '${f.name} *' : f.name;
    switch (f.type) {
      case 'dropdown':
        final options = {'': '— Select —', for (final o in f.options) o: o};
        final current = _customChoice[f.key];
        return _SelectField(
          label: label,
          value: options.containsKey(current) ? current ?? '' : '',
          options: options,
          onChange: (v) => setState(() => _customChoice[f.key] = v.isEmpty ? null : v),
        );
      case 'checkbox':
        return _SelectField(
          label: label,
          value: _customChoice[f.key] ?? '',
          options: const {'': '— Select —', 'Yes': 'Yes', 'No': 'No'},
          onChange: (v) => setState(() => _customChoice[f.key] = v.isEmpty ? null : v),
        );
      case 'date':
        final ctrl = _customText[f.key]!;
        return GestureDetector(
          onTap: () async {
            final picked = await showDatePicker(
              context: context,
              initialDate: DateTime.tryParse(ctrl.text) ?? DateTime.now(),
              firstDate: DateTime(2000),
              lastDate: DateTime(2100),
            );
            if (picked != null) {
              setState(() => ctrl.text =
                  '${picked.year}-${picked.month.toString().padLeft(2, '0')}-${picked.day.toString().padLeft(2, '0')}');
            }
          },
          child: AbsorbPointer(child: BrutalTextField(label: label, controller: ctrl, hint: 'Pick a date')),
        );
      default:
        return BrutalTextField(
          label: label,
          controller: _customText[f.key]!,
          hint: f.placeholder.isEmpty ? null : f.placeholder,
          keyboardType: switch (f.type) {
            'number' => TextInputType.number,
            'phone' => TextInputType.phone,
            'url' => TextInputType.url,
            _ => TextInputType.text,
          },
          maxLines: f.type == 'textarea' ? 3 : 1,
          minLines: f.type == 'textarea' ? 2 : 1,
        );
    }
  }

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      backgroundColor: AppColors.background,
      appBar: AppBar(
        title: Text(widget.leadId != null ? 'Edit Lead' : 'New Lead'),
        leading: IconButton(icon: const Icon(Icons.arrow_back, color: AppColors.black), onPressed: () => context.pop()),
      ),
      body: _initial
          ? const Center(child: CircularProgressIndicator(color: AppColors.yellow))
          : SingleChildScrollView(
              padding: const EdgeInsets.all(16),
              child: Column(crossAxisAlignment: CrossAxisAlignment.stretch, children: [
                _Section(title: 'Contact', icon: Icons.contact_mail, children: [
                  BrutalTextField(label: 'Full Name *', controller: _name, hint: 'Rahul Sharma'),
                  const SizedBox(height: 12),
                  BrutalTextField(label: 'Mobile Number *', controller: _phone, hint: '9876543210', keyboardType: TextInputType.phone),
                  const SizedBox(height: 12),
                  BrutalTextField(label: 'Alternate Number', controller: _altPhone, hint: 'Optional', keyboardType: TextInputType.phone),
                  const SizedBox(height: 12),
                  BrutalTextField(label: 'Email', controller: _email, hint: 'rahul@example.com', keyboardType: TextInputType.emailAddress),
                  const SizedBox(height: 12),
                  Row(children: [
                    Expanded(child: BrutalTextField(label: 'City', controller: _city, hint: 'Mumbai')),
                    const SizedBox(width: 10),
                    Expanded(child: BrutalTextField(label: 'State', controller: _state, hint: 'MH')),
                  ]),
                ]),
                const SizedBox(height: 12),
                _Section(title: 'Classification', icon: Icons.label, children: [
                  _SelectField(label: 'Source', value: _source, options: Fmt.sourceLabels, onChange: (v) => setState(() => _source = v)),
                  const SizedBox(height: 12),
                  _SelectField(label: 'Status', value: _status, options: Fmt.leadStatusLabels, onChange: (v) => setState(() => _status = v)),
                  const SizedBox(height: 12),
                  const Text('PRIORITY', style: AppTextStyles.label),
                  const SizedBox(height: 6),
                  Row(children: Fmt.priorityLabels.entries.map((m) {
                    final k = m.key;
                    final sel = _priority == k;
                    return Expanded(child: GestureDetector(
                      onTap: () => setState(() => _priority = k),
                      child: Container(
                        margin: const EdgeInsets.only(right: 6),
                        padding: const EdgeInsets.symmetric(vertical: 9),
                        decoration: BoxDecoration(
                          color: sel ? AppColors.priorityColors[k] : AppColors.white,
                          border: Border.all(color: sel ? AppColors.brand : AppColors.line, width: sel ? 1.5 : 1),
                        ),
                        child: Text(m.value, textAlign: TextAlign.center,
                            style: TextStyle(fontFamily: 'PlusJakartaSans', fontWeight: FontWeight.w700, fontSize: 11, color: sel && k == 'hot' ? AppColors.white : AppColors.black)),
                      ),
                    ));
                  }).toList()),
                ]),
                const SizedBox(height: 12),
                // Budget / Deal Value are shown and named per client — see
                // Tenants → Import fields in the platform panel.
                _Section(title: 'Sales', icon: Icons.trending_up, children: [
                  if (_config.budget.show) ...[
                    BrutalTextField(label: _config.budget.label, controller: _budget, hint: '500000', keyboardType: TextInputType.number),
                    const SizedBox(height: 12),
                  ],
                  if (_config.dealValue.show) ...[
                    BrutalTextField(label: _config.dealValue.label, controller: _deal, hint: '250000', keyboardType: TextInputType.number),
                    const SizedBox(height: 12),
                  ],
                  BrutalTextField(label: 'Requirement', controller: _req, hint: 'What does the lead need?', maxLines: 3, minLines: 2),
                ]),
                if (_config.customFields.isNotEmpty) ...[
                  const SizedBox(height: 12),
                  _Section(title: 'More details', icon: Icons.tune, children: [
                    for (final f in _config.customFields) ...[
                      _customInput(f),
                      const SizedBox(height: 12),
                    ],
                  ]),
                ],
                const SizedBox(height: 24),
                BrutalButton.primary(
                  label: _loading ? 'Saving…' : (widget.leadId != null ? 'Save Changes →' : 'Create Lead →'),
                  isLoading: _loading,
                  onPressed: _loading ? null : _submit,
                ),
                const SizedBox(height: 40),
              ]),
            ),
    );
  }
}

class _Section extends StatelessWidget {
  final String title;
  final IconData icon;
  final List<Widget> children;
  const _Section({required this.title, required this.icon, required this.children});

  @override
  Widget build(BuildContext context) => BrutalCard(
    padding: EdgeInsets.zero,
    child: Column(crossAxisAlignment: CrossAxisAlignment.stretch, children: [
      Container(
        padding: const EdgeInsets.symmetric(horizontal: 14, vertical: 10),
        decoration: const BoxDecoration( border: Border(bottom: BorderSide(color: AppColors.line, width: 1))),
        child: Row(children: [
          Icon(icon, size: 16, color: AppColors.brand),
          const SizedBox(width: 8),
          Text(title, style: const TextStyle(fontFamily: 'PlusJakartaSans', fontWeight: FontWeight.w700, fontSize: 14, color: AppColors.brand)),
        ]),
      ),
      Padding(padding: const EdgeInsets.all(14), child: Column(children: children)),
    ]),
  );
}

class _SelectField extends StatelessWidget {
  final String label, value;
  final Map<String, String> options;
  final ValueChanged<String> onChange;
  const _SelectField({required this.label, required this.value, required this.options, required this.onChange});

  @override
  Widget build(BuildContext context) => Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
    Text(label.toUpperCase(), style: AppTextStyles.label),
    const SizedBox(height: 6),
    Container(
      decoration: BoxDecoration(
        color: AppColors.white,
        border: Border.all(color: AppColors.line, width: 1),
        boxShadow: const [BoxShadow(color: Color(0x1F111A16), offset: Offset(0, 6), blurRadius: 18, spreadRadius: -8)],
      ),
      padding: const EdgeInsets.symmetric(horizontal: 14),
      child: DropdownButtonHideUnderline(child: DropdownButton<String>(
        value: value, isExpanded: true,
        items: options.entries.map((e) => DropdownMenuItem(value: e.key, child: Text(e.value, style: const TextStyle(fontFamily: 'PlusJakartaSans', fontSize: 14)))).toList(),
        onChanged: (v) { if (v != null) onChange(v); },
        style: const TextStyle(fontFamily: 'PlusJakartaSans', fontSize: 14, color: AppColors.black),
        icon: const Icon(Icons.arrow_drop_down, color: AppColors.black),
      )),
    ),
  ]);
}
