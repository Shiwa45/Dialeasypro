// ============================================================
// DialEasypro — A lead's custom fields
//
// One widget for both places that need them — lead detail and the dialer —
// so the two cannot drift into showing different things.
//
// Custom fields are what a sales team actually qualifies on: property type,
// budget range, preferred locality. The server has always sent them on the
// lead detail and on the dialer's queue pull. The app never parsed them, so an
// agent on a call had no sight of the answers the lead had already given.
// ============================================================
import 'package:flutter/material.dart';

import '../../core/theme/colors.dart';
import '../../core/widgets/widgets.dart';
import '../../data/models/models.dart';
import '../../data/services/services.dart';

/// Shows [lead]'s custom fields, fetching the full lead first when [lead]
/// came from a response that did not include them.
class LeadCustomFields extends StatefulWidget {
  const LeadCustomFields({
    super.key,
    required this.lead,
    this.compact = false,
    this.title = 'Details',
  });

  final Lead lead;

  /// A tighter layout for the dialer, where it sits under a live call and has
  /// to be read at a glance rather than studied.
  final bool compact;

  final String title;

  @override
  State<LeadCustomFields> createState() => _LeadCustomFieldsState();
}

class _LeadCustomFieldsState extends State<LeadCustomFields> {
  List<LeadCustomField>? _fields;
  bool _loading = false;

  @override
  void initState() {
    super.initState();
    _prime();
  }

  @override
  void didUpdateWidget(covariant LeadCustomFields old) {
    super.didUpdateWidget(old);
    // The dialer reuses this widget as it moves from one lead to the next.
    // Without this it would keep showing the previous lead's answers.
    if (old.lead.id != widget.lead.id ||
        old.lead.customFieldsLoaded != widget.lead.customFieldsLoaded) {
      _prime();
    }
  }

  /// Set state for the current lead synchronously, and start a fetch only if
  /// the lead arrived without its custom fields.
  ///
  /// Assigns fields directly rather than through setState: this runs from
  /// initState and didUpdateWidget, both of which are followed by a build
  /// anyway, and calling setState from initState is not allowed.
  void _prime() {
    if (widget.lead.customFieldsLoaded) {
      _fields = widget.lead.customFields;
      _loading = false;
      return;
    }
    _fields = null;
    _loading = true;
    _fetch();
  }

  Future<void> _fetch() async {
    // Taken from the leads list, which omits custom fields to stay light.
    // Showing "none" here would be a lie, so fetch the lead properly.
    final forId = widget.lead.id;
    try {
      final full = await LeadsService.instance.getLead(forId);
      // The dialer may have advanced to another lead while this was in flight.
      if (!mounted || widget.lead.id != forId) return;
      setState(() {
        _fields = full.customFields;
        _loading = false;
      });
    } catch (_) {
      if (!mounted || widget.lead.id != forId) return;
      // A failed fetch leaves the panel off rather than claiming there is
      // nothing to show.
      setState(() {
        _fields = const [];
        _loading = false;
      });
    }
  }

  @override
  Widget build(BuildContext context) {
    if (_loading) {
      return widget.compact
          ? const SizedBox.shrink()
          : const Padding(
              padding: EdgeInsets.symmetric(vertical: 12),
              child: Center(
                child: SizedBox(
                  width: 18, height: 18,
                  child: CircularProgressIndicator(strokeWidth: 2),
                ),
              ),
            );
    }

    // Only fields that were actually answered. A row reading "Budget range: —"
    // is noise on a call, and the web detail view skips blanks the same way.
    final answered = (_fields ?? const <LeadCustomField>[])
        .where((f) => f.value.trim().isNotEmpty)
        .toList();
    if (answered.isEmpty) return const SizedBox.shrink();

    return BrutalCard(
      padding: EdgeInsets.all(widget.compact ? 12 : 16),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Row(children: [
            Icon(Icons.tune, size: widget.compact ? 14 : 16, color: AppColors.brand),
            const SizedBox(width: 6),
            Text(
              widget.title.toUpperCase(),
              style: TextStyle(
                fontFamily: 'PlusJakartaSans', fontWeight: FontWeight.w700,
                fontSize: widget.compact ? 10 : 11,
                letterSpacing: 0.6, color: AppColors.text3,
              ),
            ),
          ]),
          SizedBox(height: widget.compact ? 8 : 10),
          for (var i = 0; i < answered.length; i++) ...[
            if (i > 0)
              Divider(height: widget.compact ? 12 : 16, color: AppColors.line),
            _Row(field: answered[i], compact: widget.compact),
          ],
        ],
      ),
    );
  }
}

class _Row extends StatelessWidget {
  const _Row({required this.field, required this.compact});

  final LeadCustomField field;
  final bool compact;

  @override
  Widget build(BuildContext context) {
    return Row(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        // A fixed label column, so values line up down the card and a long
        // field name wraps rather than shoving its value off the edge.
        SizedBox(
          width: compact ? 110 : 128,
          child: Text(
            field.name,
            style: TextStyle(
              fontFamily: 'PlusJakartaSans',
              fontSize: compact ? 12 : 13,
              color: AppColors.text2,
            ),
          ),
        ),
        const SizedBox(width: 8),
        Expanded(
          child: Text(
            field.value,
            style: TextStyle(
              fontFamily: 'PlusJakartaSans',
              fontWeight: FontWeight.w600,
              fontSize: compact ? 13 : 14,
              color: AppColors.text,
            ),
          ),
        ),
      ],
    );
  }
}
