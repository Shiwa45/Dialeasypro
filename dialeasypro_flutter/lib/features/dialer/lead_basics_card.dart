import 'package:flutter/material.dart';
import '../../core/theme/colors.dart';
import '../../core/utils/utils.dart';
import '../../core/widgets/widgets.dart';
import '../../data/models/models.dart';

// ============================================================
// DialEasypro — Lead basics on the dialing screens
//
// The dialer showed a lead's name, number, status and city, and nothing else
// — the source, budget, email, how often we have called and when we last
// did were all on the lead detail screen, which an agent cannot open while
// the auto-dialer is running. This puts the basics in front of them before,
// during and after the call. Empty values are left out rather than shown as
// dashes, so a sparse lead stays a short card.
// ============================================================

class LeadBasicsCard extends StatelessWidget {
  final Lead lead;
  const LeadBasicsCard({super.key, required this.lead});

  @override
  Widget build(BuildContext context) {
    final rows = <(IconData, String, String)>[
      if (lead.sourceDisplay.isNotEmpty) (Icons.campaign_outlined, 'Source', lead.sourceDisplay),
      if (_has(lead.budget)) (Icons.account_balance_wallet_outlined, 'Budget', Fmt.inr(lead.budget)),
      if (_has(lead.dealValue)) (Icons.handshake_outlined, 'Deal value', Fmt.inr(lead.dealValue)),
      if (lead.email.isNotEmpty) (Icons.mail_outline, 'Email', lead.email),
      if (lead.alternatePhone.isNotEmpty)
        (Icons.phone_forwarded_outlined, 'Alt. phone', Fmt.displayPhone(lead.alternatePhone)),
      if ([lead.city, lead.state].any((v) => v.isNotEmpty))
        (Icons.place_outlined, 'Location', [lead.city, lead.state].where((v) => v.isNotEmpty).join(', ')),
      (Icons.call_made, 'Called before', lead.contactCount == 0 ? 'Never' : '${lead.contactCount}×'),
      if (_has(lead.lastContactedAt)) (Icons.history, 'Last contact', Fmt.relative(lead.lastContactedAt)),
      if (_has(lead.nextFollowupAt))
        (Icons.event_outlined, lead.followupOverdue ? 'Follow-up (overdue)' : 'Follow-up',
         Fmt.dateTime(lead.nextFollowupAt)),
      if (_has(lead.assignedToName)) (Icons.person_outline, 'Assigned to', lead.assignedToName!),
    ];

    return BrutalCard(
      padding: const EdgeInsets.fromLTRB(14, 12, 14, 8),
      color: AppColors.white,
      child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
        const Text('LEAD BASICS', style: AppTextStyles.label),
        const SizedBox(height: 6),
        for (final (icon, label, value) in rows)
          Padding(
            padding: const EdgeInsets.symmetric(vertical: 4),
            child: Row(crossAxisAlignment: CrossAxisAlignment.start, children: [
              Icon(icon, size: 15, color: AppColors.text2),
              const SizedBox(width: 8),
              SizedBox(
                width: 108,
                child: Text(label, style: const TextStyle(
                  fontFamily: 'PlusJakartaSans', fontSize: 12, color: AppColors.text2)),
              ),
              Expanded(child: Text(value, style: TextStyle(
                fontFamily: 'PlusJakartaSans', fontSize: 12.5, fontWeight: FontWeight.w600,
                color: label.contains('overdue') ? AppColors.error : AppColors.black))),
            ]),
          ),
        if (lead.tags.isNotEmpty) ...[
          const SizedBox(height: 6),
          Wrap(spacing: 6, runSpacing: 6, children: [
            for (final t in lead.tags) TagChip(label: t, backgroundColor: AppColors.brand50, textColor: AppColors.brand),
          ]),
          const SizedBox(height: 4),
        ],
      ]),
    );
  }

  static bool _has(String? v) => v != null && v.isNotEmpty && v != 'null';
}
