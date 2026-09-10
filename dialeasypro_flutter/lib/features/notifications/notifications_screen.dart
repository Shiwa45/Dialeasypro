// ============================================================
// DialEasypro — Notifications
//
// What the agent has been told, and what is still unread. Pull to refresh
// also re-arms the local reminders, so the one gesture that means "catch me
// up" reconciles the phone's alarm list with the server at the same time.
// ============================================================
import 'package:flutter/material.dart';
import 'package:go_router/go_router.dart';
import 'package:timeago/timeago.dart' as timeago;

import '../../core/services/notification_service.dart';
import '../../data/models/models.dart';
import '../../data/services/services.dart';

class NotificationsScreen extends StatefulWidget {
  const NotificationsScreen({super.key});

  @override
  State<NotificationsScreen> createState() => _NotificationsScreenState();
}

class _NotificationsScreenState extends State<NotificationsScreen> {
  List<AppNotification> _rows = const [];
  bool _loading = true;
  String? _error;

  @override
  void initState() {
    super.initState();
    _load();
  }

  Future<void> _load() async {
    setState(() => _error = null);
    try {
      final rows = await NotificationsService.instance.list(pageSize: 50);
      if (!mounted) return;
      setState(() {
        _rows = rows;
        _loading = false;
      });
    } catch (e) {
      if (!mounted) return;
      setState(() {
        _error = 'Could not load notifications.';
        _loading = false;
      });
    }
  }

  Future<void> _refresh() async {
    await _load();
    // Reconcile the OS alarms while we are here. A follow-up completed or
    // moved on the web would otherwise still fire on this phone.
    await NotificationService.instance.syncFollowupReminders();
  }

  Future<void> _markAllRead() async {
    try {
      await NotificationsService.instance.markAllRead();
      await _load();
    } catch (_) {
      if (!mounted) return;
      ScaffoldMessenger.of(context).showSnackBar(
        const SnackBar(content: Text('Could not mark them read.')),
      );
    }
  }

  Future<void> _open(AppNotification n) async {
    if (!n.isRead) {
      // Fire and forget: a failed read-receipt must not block navigation.
      NotificationsService.instance.markRead(n.id).catchError((_) {});
      setState(() {
        _rows = _rows
            .map((r) => r.id == n.id
                ? AppNotification(
                    id: r.id, kind: r.kind, title: r.title, body: r.body,
                    url: r.url, leadId: r.leadId, followupId: r.followupId,
                    isRead: true, createdAt: r.createdAt)
                : r)
            .toList();
      });
    }
    if (!mounted) return;
    if (n.url.isNotEmpty) context.push(n.url);
  }

  @override
  Widget build(BuildContext context) {
    final unread = _rows.where((r) => !r.isRead).length;

    return Scaffold(
      appBar: AppBar(
        title: const Text('Notifications'),
        actions: [
          if (unread > 0)
            TextButton(
              onPressed: _markAllRead,
              child: const Text('Mark all read'),
            ),
        ],
      ),
      body: RefreshIndicator(
        onRefresh: _refresh,
        child: _loading
            ? const Center(child: CircularProgressIndicator())
            : _error != null
                ? _Blank(text: _error!, action: _load)
                : _rows.isEmpty
                    ? const _Blank(
                        text: 'Nothing yet.\n\nFollow-ups scheduled on your '
                            'leads show up here, and a reminder is set on this '
                            'phone for each one.')
                    : ListView.separated(
                        physics: const AlwaysScrollableScrollPhysics(),
                        itemCount: _rows.length,
                        separatorBuilder: (_, __) => const Divider(height: 1),
                        itemBuilder: (_, i) => _Row(
                          notification: _rows[i],
                          onTap: () => _open(_rows[i]),
                        ),
                      ),
      ),
    );
  }
}

class _Row extends StatelessWidget {
  const _Row({required this.notification, required this.onTap});

  final AppNotification notification;
  final VoidCallback onTap;

  // Each kind gets the colour that already means that thing elsewhere in the
  // app rather than a decorative one.
  (IconData, Color) get _look => switch (notification.kind) {
        'followup_overdue' => (Icons.warning_amber_rounded, const Color(0xFFCE3A22)),
        'followup_due' => (Icons.schedule, const Color(0xFFCF8A06)),
        'followup_scheduled' => (Icons.event_available, const Color(0xFF0B5F55)),
        'lead_assigned' => (Icons.person_add_alt, const Color(0xFF6244B8)),
        _ => (Icons.info_outline, const Color(0xFF5C6A62)),
      };

  @override
  Widget build(BuildContext context) {
    final (icon, colour) = _look;
    final at = notification.createdAtLocal;

    return ListTile(
      onTap: onTap,
      tileColor: notification.isRead ? null : colour.withValues(alpha: 0.06),
      leading: CircleAvatar(
        backgroundColor: colour.withValues(alpha: 0.14),
        child: Icon(icon, size: 18, color: colour),
      ),
      title: Text(
        notification.title,
        style: TextStyle(
          fontSize: 14,
          fontWeight: notification.isRead ? FontWeight.w500 : FontWeight.w700,
        ),
      ),
      subtitle: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          if (notification.body.isNotEmpty)
            Padding(
              padding: const EdgeInsets.only(top: 2),
              child: Text(notification.body,
                  maxLines: 2, overflow: TextOverflow.ellipsis,
                  style: const TextStyle(fontSize: 12.5)),
            ),
          if (at != null)
            Padding(
              padding: const EdgeInsets.only(top: 4),
              child: Text(timeago.format(at),
                  style: const TextStyle(fontSize: 11, color: Color(0xFF8B968F))),
            ),
        ],
      ),
      trailing: notification.isRead
          ? null
          : Icon(Icons.circle, size: 9, color: colour),
      isThreeLine: notification.body.isNotEmpty,
    );
  }
}

class _Blank extends StatelessWidget {
  const _Blank({required this.text, this.action});

  final String text;
  final VoidCallback? action;

  @override
  Widget build(BuildContext context) {
    // Inside a ListView so pull-to-refresh still works on an empty screen.
    return ListView(
      physics: const AlwaysScrollableScrollPhysics(),
      children: [
        const SizedBox(height: 120),
        Padding(
          padding: const EdgeInsets.symmetric(horizontal: 36),
          child: Text(text,
              textAlign: TextAlign.center,
              style: const TextStyle(fontSize: 13.5, color: Color(0xFF5C6A62), height: 1.6)),
        ),
        if (action != null)
          Padding(
            padding: const EdgeInsets.only(top: 18),
            child: Center(
              child: OutlinedButton(onPressed: action, child: const Text('Try again')),
            ),
          ),
      ],
    );
  }
}
