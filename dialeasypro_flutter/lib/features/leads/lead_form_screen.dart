import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:go_router/go_router.dart';
import '../../core/theme/colors.dart';
import '../../core/utils/utils.dart';
import '../../core/widgets/widgets.dart';
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
  String _priority = 'medium';
  bool _loading = false;
  bool _initial = false;

  @override
  void initState() {
    super.initState();
    if (widget.leadId != null) _load();
  }

  Future<void> _load() async {
    setState(() => _initial = true);
    try {
      final l = await LeadsService.instance.getLead(widget.leadId!);
      _name.text = l.name; _phone.text = l.phone; _altPhone.text = l.alternatePhone;
      _email.text = l.email; _city.text = l.city; _state.text = l.state;
      _req.text = l.requirement; _budget.text = l.budget ?? ''; _deal.text = l.dealValue ?? '';
      setState(() { _source = l.source; _status = l.status; _priority = l.priority; _initial = false; });
    } catch (_) { setState(() => _initial = false); }
  }

  @override
  void dispose() {
    for (final c in [_name, _phone, _altPhone, _email, _city, _state, _req, _budget, _deal]) c.dispose();
    super.dispose();
  }

  Future<void> _submit() async {
    if (_name.text.trim().isEmpty || _phone.text.trim().isEmpty) {
      AppToast.show(context, 'Name and phone required', isError: true);
      return;
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
      if (_budget.text.isNotEmpty) 'budget': _budget.text.trim(),
      if (_deal.text.isNotEmpty) 'deal_value': _deal.text.trim(),
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
      if (mounted) AppToast.show(context, 'Failed', isError: true);
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
                  Row(children: [
                    {'hot': '🔥 Hot'}, {'high': 'High'}, {'medium': 'Medium'}, {'low': 'Low'},
                  ].map((m) {
                    final k = m.keys.first;
                    final sel = _priority == k;
                    return Expanded(child: GestureDetector(
                      onTap: () => setState(() => _priority = k),
                      child: Container(
                        margin: const EdgeInsets.only(right: 6),
                        padding: const EdgeInsets.symmetric(vertical: 9),
                        decoration: BoxDecoration(
                          color: sel ? AppColors.priorityColors[k] : AppColors.white,
                          border: Border.all(color: AppColors.black, width: sel ? 2 : 1.5),
                        ),
                        child: Text(m.values.first, textAlign: TextAlign.center,
                            style: TextStyle(fontFamily: 'SpaceGrotesk', fontWeight: FontWeight.w700, fontSize: 11, color: sel && (k == 'hot' || k == 'high') ? AppColors.white : AppColors.black)),
                      ),
                    ));
                  }).toList()),
                ]),
                const SizedBox(height: 12),
                _Section(title: 'Sales', icon: Icons.trending_up, children: [
                  BrutalTextField(label: 'Budget (₹)', controller: _budget, hint: '500000', keyboardType: TextInputType.number),
                  const SizedBox(height: 12),
                  BrutalTextField(label: 'Deal Value (₹)', controller: _deal, hint: '250000', keyboardType: TextInputType.number),
                  const SizedBox(height: 12),
                  BrutalTextField(label: 'Requirement', controller: _req, hint: 'What does the lead need?', maxLines: 3, minLines: 2),
                ]),
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
        decoration: const BoxDecoration(color: AppColors.dark, border: Border(bottom: BorderSide(color: AppColors.black, width: 2))),
        child: Row(children: [
          Icon(icon, size: 16, color: AppColors.yellow),
          const SizedBox(width: 8),
          Text(title, style: const TextStyle(fontFamily: 'SpaceGrotesk', fontWeight: FontWeight.w700, fontSize: 14, color: AppColors.yellow)),
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
        border: Border.all(color: AppColors.black, width: 2),
        boxShadow: const [BoxShadow(color: AppColors.black, offset: Offset(3, 3))],
      ),
      padding: const EdgeInsets.symmetric(horizontal: 14),
      child: DropdownButtonHideUnderline(child: DropdownButton<String>(
        value: value, isExpanded: true,
        items: options.entries.map((e) => DropdownMenuItem(value: e.key, child: Text(e.value, style: const TextStyle(fontFamily: 'DMSans', fontSize: 14)))).toList(),
        onChanged: (v) { if (v != null) onChange(v); },
        style: const TextStyle(fontFamily: 'DMSans', fontSize: 14, color: AppColors.black),
        icon: const Icon(Icons.arrow_drop_down, color: AppColors.black),
      )),
    ),
  ]);
}
