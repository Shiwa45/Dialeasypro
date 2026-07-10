import 'package:intl/intl.dart';
import 'package:timeago/timeago.dart' as timeago;

class Fmt {
  Fmt._();

  static final _date = DateFormat('dd MMM yyyy');
  static final _dateTime = DateFormat('dd MMM yyyy, hh:mm a');
  static final _time = DateFormat('hh:mm a');

  static String date(String? iso) {
    if (iso == null || iso.isEmpty) return '—';
    try { return _date.format(DateTime.parse(iso).toLocal()); } catch (_) { return iso; }
  }

  static String dateTime(String? iso) {
    if (iso == null || iso.isEmpty) return '—';
    try { return _dateTime.format(DateTime.parse(iso).toLocal()); } catch (_) { return iso; }
  }

  static String time(String? iso) {
    if (iso == null || iso.isEmpty) return '—';
    try { return _time.format(DateTime.parse(iso).toLocal()); } catch (_) { return iso; }
  }

  static String relative(String? iso) {
    if (iso == null || iso.isEmpty) return '—';
    try { return timeago.format(DateTime.parse(iso).toLocal()); } catch (_) { return iso; }
  }

  static String duration(int seconds) {
    if (seconds <= 0) return '—';
    final m = seconds ~/ 60;
    final s = seconds % 60;
    if (m == 0) return '${s}s';
    return '${m}m ${s.toString().padLeft(2, '0')}s';
  }

  /// Format duration as MM:SS for call timer display
  static String timer(int seconds) {
    final m = seconds ~/ 60;
    final s = seconds % 60;
    return '${m.toString().padLeft(2, '0')}:${s.toString().padLeft(2, '0')}';
  }

  static String inr(dynamic amount) {
    if (amount == null) return '—';
    final n = num.tryParse(amount.toString()) ?? 0;
    if (n >= 10000000) return '₹${(n / 10000000).toStringAsFixed(1)}Cr';
    if (n >= 100000) return '₹${(n / 100000).toStringAsFixed(1)}L';
    if (n >= 1000) return '₹${(n / 1000).toStringAsFixed(1)}K';
    return '₹${n.toStringAsFixed(0)}';
  }

  static String normalizePhone(String phone) {
    final d = phone.replaceAll(RegExp(r'[^\d+]'), '');
    if (d.startsWith('+91') && d.length == 13) return d;
    if (d.startsWith('91') && d.length == 12) return '+$d';
    if (d.length == 10) return '+91$d';
    return phone;
  }

  static String displayPhone(String phone) {
    final n = normalizePhone(phone);
    if (n.startsWith('+91') && n.length == 13) return '+91 ${n.substring(3, 8)} ${n.substring(8)}';
    return phone;
  }

  static const leadStatusLabels = {
    'new': 'New', 'attempted': 'Attempted', 'contacted': 'Contacted',
    'interested': 'Interested', 'not_interested': 'Not Interested',
    'follow_up': 'Follow-up', 'negotiation': 'Negotiation',
    'converted': 'Converted', 'lost': 'Lost', 'duplicate': 'Duplicate',
  };

  static const sourceLabels = {
    'manual': 'Manual', 'indiamart': 'IndiaMART', 'meta_facebook': 'Meta Ads',
    'google_ads': 'Google Ads', 'website': 'Website', 'referral': 'Referral',
    'csv_import': 'CSV', 'webhook': 'Webhook', 'other': 'Other',
  };
}

class Validators {
  static String? required(String? v, [String f = 'Field']) =>
      (v == null || v.trim().isEmpty) ? '$f is required.' : null;

  static String? email(String? v) {
    if (v == null || v.isEmpty) return 'Email is required.';
    if (!RegExp(r'^[^@]+@[^@]+\.[^@]+').hasMatch(v)) return 'Invalid email.';
    return null;
  }

  static String? phone(String? v) {
    if (v == null || v.isEmpty) return 'Phone is required.';
    final d = v.replaceAll(RegExp(r'[^\d]'), '');
    if (d.length < 10) return 'Enter 10-digit mobile.';
    return null;
  }
}
