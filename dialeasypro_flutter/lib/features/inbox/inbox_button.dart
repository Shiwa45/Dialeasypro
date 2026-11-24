// ============================================================
// DialSathi — WhatsApp inbox button
//
// An app-bar icon with the number of conversations waiting for a reply.
// Polled, like the notification bell beside it: the count only has to be
// roughly right while the app is open, and the server's whatsapp_reply
// notification is what reaches a phone that is not looking.
// ============================================================
import 'dart:async';

import 'package:flutter/material.dart';
import 'package:go_router/go_router.dart';

import '../../core/theme/colors.dart';
import '../../data/services/services.dart';

class InboxButton extends StatefulWidget {
  const InboxButton({super.key, this.color});

  final Color? color;

  @override
  State<InboxButton> createState() => _InboxButtonState();
}

class _InboxButtonState extends State<InboxButton> with WidgetsBindingObserver {
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
    if (state == AppLifecycleState.resumed) _refresh();
  }

  Future<void> _refresh() async {
    try {
      final n = await InboxService.instance.unreadConversations();
      if (!mounted) return;
      setState(() => _unread = n);
    } catch (_) {
      // Offline, signed out, or WhatsApp not set up: no badge.
    }
  }

  @override
  Widget build(BuildContext context) {
    return Stack(
      clipBehavior: Clip.none,
      children: [
        IconButton(
          icon: Icon(
            _unread > 0 ? Icons.mark_chat_unread : Icons.chat_bubble_outline,
            color: widget.color ?? AppColors.black,
          ),
          tooltip: _unread > 0 ? '$_unread WhatsApp conversations to answer' : 'WhatsApp inbox',
          onPressed: () async {
            await context.push('/inbox');
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
                  color: AppColors.won,
                  borderRadius: BorderRadius.circular(999),
                  border: Border.all(color: AppColors.surface, width: 1.5),
                ),
                child: Text(
                  _unread > 99 ? '99+' : '$_unread',
                  textAlign: TextAlign.center,
                  style: const TextStyle(color: Colors.white, fontSize: 9.5, fontWeight: FontWeight.w700, height: 1.3),
                ),
              ),
            ),
          ),
      ],
    );
  }
}
