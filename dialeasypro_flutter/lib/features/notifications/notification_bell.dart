// ============================================================
// DialEasypro — Notification bell
//
// The dashboard had a bell with `onPressed: () {}` behind it, so the
// notifications screen was unreachable and the unread count was never shown
// anywhere. An agent had no way to find out that a follow-up had been
// scheduled on their lead except by opening that lead.
//
// The count is polled rather than pushed. The phone's reliable path for
// anything time-based is the local alarm the app arms with Android; this
// badge only has to be roughly right while the app is open, and a poll
// survives a dropped socket without any reconnect logic to get wrong.
// ============================================================
import 'dart:async';

import 'package:flutter/material.dart';
import 'package:go_router/go_router.dart';

import '../../core/theme/colors.dart';
import '../../data/services/services.dart';

class NotificationBell extends StatefulWidget {
  const NotificationBell({super.key, this.color});

  final Color? color;

  @override
  State<NotificationBell> createState() => _NotificationBellState();
}

class _NotificationBellState extends State<NotificationBell>
    with WidgetsBindingObserver {
  static const _interval = Duration(minutes: 1);

  int _unread = 0;
  Timer? _timer;

  @override
  void initState() {
    super.initState();
    WidgetsBinding.instance.addObserver(this);
    _refresh();
    _timer = Timer.periodic(_interval, (_) => _refresh());
  }

  @override
  void dispose() {
    WidgetsBinding.instance.removeObserver(this);
    _timer?.cancel();
    super.dispose();
  }

  @override
  void didChangeAppLifecycleState(AppLifecycleState state) {
    // Coming back to the app is the moment the count is most likely stale —
    // a reminder may well have fired while it was in the background.
    if (state == AppLifecycleState.resumed) _refresh();
  }

  Future<void> _refresh() async {
    try {
      final n = await NotificationsService.instance.unreadCount();
      if (!mounted) return;
      setState(() => _unread = n);
    } catch (_) {
      // Offline, or the agent is signed out. A badge is not worth an error.
    }
  }

  @override
  Widget build(BuildContext context) {
    return Stack(
      clipBehavior: Clip.none,
      children: [
        IconButton(
          icon: Icon(
            _unread > 0 ? Icons.notifications_active : Icons.notifications_outlined,
            color: widget.color ?? AppColors.black,
          ),
          tooltip: _unread > 0 ? '$_unread unread' : 'Notifications',
          onPressed: () async {
            await context.push('/notifications');
            // Whatever was read in there changes the badge.
            _refresh();
          },
        ),
        if (_unread > 0)
          Positioned(
            right: 6,
            top: 6,
            child: IgnorePointer(
              child: Container(
                padding: const EdgeInsets.symmetric(horizontal: 4, vertical: 1),
                constraints: const BoxConstraints(minWidth: 16),
                decoration: BoxDecoration(
                  color: AppColors.hot,
                  borderRadius: BorderRadius.circular(999),
                  border: Border.all(color: AppColors.surface, width: 1.5),
                ),
                child: Text(
                  _unread > 99 ? '99+' : '$_unread',
                  textAlign: TextAlign.center,
                  style: const TextStyle(
                    color: Colors.white,
                    fontSize: 9.5,
                    fontWeight: FontWeight.w700,
                    height: 1.3,
                  ),
                ),
              ),
            ),
          ),
      ],
    );
  }
}
