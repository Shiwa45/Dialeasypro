// ============================================================
// DialSathi — WhatsApp inbox
//
// The customers who have written to the company's WhatsApp numbers, newest
// conversation first, with what is unread — scoped by the server to the
// agent's own leads. Before this a reply was only visible to somebody who
// opened that lead's WhatsApp history on the web.
//
// Polled rather than pushed, like the notification bell: a poll survives a
// dropped socket, and the phone is told about a new reply by the server's
// notification (whatsapp_reply) anyway.
// ============================================================
import 'dart:async';

import 'package:flutter/material.dart';
import 'package:go_router/go_router.dart';

import '../../core/theme/colors.dart';
import '../../core/widgets/widgets.dart';
import '../../data/models/models.dart';
import '../../data/services/services.dart';

/// 10:42 today, "Yesterday", or 21 Nov.
String inboxListTime(DateTime? at, DateTime now) {
  if (at == null) return '';
  final today = DateTime(now.year, now.month, now.day);
  final day = DateTime(at.year, at.month, at.day);
  if (day == today) {
    final h = at.hour % 12 == 0 ? 12 : at.hour % 12;
    return '$h:${at.minute.toString().padLeft(2, '0')} ${at.hour < 12 ? 'am' : 'pm'}';
  }
  if (today.difference(day).inDays == 1) return 'Yesterday';
  const months = ['Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun', 'Jul', 'Aug', 'Sep', 'Oct', 'Nov', 'Dec'];
  return '${at.day} ${months[at.month - 1]}';
}

class InboxScreen extends StatefulWidget {
  const InboxScreen({super.key});

  @override
  State<InboxScreen> createState() => _InboxScreenState();
}

class _InboxScreenState extends State<InboxScreen> with WidgetsBindingObserver {
  List<InboxConversation> _rows = const [];
  bool _loading = true;
  String? _error;
  bool _unreadOnly = false;
  String _search = '';
  bool _showSearch = false;
  Timer? _poll;
  Timer? _debounce;
  final _searchCtrl = TextEditingController();

  @override
  void initState() {
    super.initState();
    WidgetsBinding.instance.addObserver(this);
    _load();
    _poll = Timer.periodic(const Duration(seconds: 45), (_) => _load(quiet: true));
  }

  @override
  void dispose() {
    WidgetsBinding.instance.removeObserver(this);
    _poll?.cancel();
    _debounce?.cancel();
    _searchCtrl.dispose();
    super.dispose();
  }

  @override
  void didChangeAppLifecycleState(AppLifecycleState state) {
    if (state == AppLifecycleState.resumed) _load(quiet: true);
  }

  Future<void> _load({bool quiet = false}) async {
    if (!quiet) setState(() => _error = null);
    try {
      final rows = await InboxService.instance.list(unreadOnly: _unreadOnly, search: _search);
      if (!mounted) return;
      setState(() {
        _rows = rows;
        _loading = false;
        _error = null;
      });
    } catch (_) {
      if (!mounted) return;
      setState(() {
        _loading = false;
        if (!quiet || _rows.isEmpty) _error = 'Could not load the inbox. Pull down to try again.';
      });
    }
  }

  Future<void> _open(InboxConversation c) async {
    await context.push('/inbox/${c.leadId}');
    _load(quiet: true);
  }

  @override
  Widget build(BuildContext context) {
    final now = DateTime.now();
    return Scaffold(
      backgroundColor: AppColors.background,
      appBar: AppBar(
        title: _showSearch
            ? TextField(
                controller: _searchCtrl,
                autofocus: true,
                style: const TextStyle(fontFamily: 'PlusJakartaSans', fontSize: 14),
                decoration: const InputDecoration(
                  hintText: 'Search name or phone…', border: InputBorder.none,
                  hintStyle: TextStyle(color: AppColors.grey),
                ),
                onChanged: (v) {
                  _debounce?.cancel();
                  _debounce = Timer(const Duration(milliseconds: 400), () {
                    _search = v;
                    _load();
                  });
                },
              )
            : const Text('WhatsApp Inbox'),
        actions: [
          IconButton(
            icon: Icon(_showSearch ? Icons.close : Icons.search, color: AppColors.black),
            tooltip: _showSearch ? 'Close search' : 'Search',
            onPressed: () {
              setState(() => _showSearch = !_showSearch);
              if (!_showSearch && _search.isNotEmpty) {
                _searchCtrl.clear();
                _search = '';
                _load();
              }
            },
          ),
        ],
      ),
      body: Column(
        children: [
          Padding(
            padding: const EdgeInsets.fromLTRB(16, 10, 16, 6),
            child: Row(children: [
              _FilterChip(label: 'All', on: !_unreadOnly, onTap: () {
                setState(() => _unreadOnly = false);
                _load();
              }),
              const SizedBox(width: 8),
              _FilterChip(label: 'Unread', on: _unreadOnly, onTap: () {
                setState(() => _unreadOnly = true);
                _load();
              }),
            ]),
          ),
          Expanded(
            child: RefreshIndicator(
              onRefresh: _load,
              child: _body(now),
            ),
          ),
        ],
      ),
    );
  }

  Widget _body(DateTime now) {
    if (_loading) return const Center(child: CircularProgressIndicator());
    if (_error != null && _rows.isEmpty) {
      return ListView(children: [
        const SizedBox(height: 80),
        EmptyStateView(icon: Icons.cloud_off, title: 'Inbox unavailable', message: _error),
      ]);
    }
    if (_rows.isEmpty) {
      return ListView(children: [
        const SizedBox(height: 60),
        EmptyStateView(
          icon: Icons.mark_chat_read_outlined,
          iconColor: AppColors.brand,
          title: _unreadOnly ? 'All caught up' : 'No conversations yet',
          message: _unreadOnly
              ? 'Nothing is waiting for a reply.'
              : _search.isNotEmpty
                  ? 'No conversation matches “$_search”.'
                  : 'When a customer replies to your WhatsApp messages, the conversation appears here.',
        ),
      ]);
    }
    return ListView.separated(
      itemCount: _rows.length,
      separatorBuilder: (_, __) => const Divider(height: 1, color: AppColors.line),
      itemBuilder: (_, i) => _Row(c: _rows[i], now: now, onTap: () => _open(_rows[i])),
    );
  }
}

class _FilterChip extends StatelessWidget {
  const _FilterChip({required this.label, required this.on, required this.onTap});
  final String label;
  final bool on;
  final VoidCallback onTap;

  @override
  Widget build(BuildContext context) {
    return InkWell(
      borderRadius: BorderRadius.circular(999),
      onTap: onTap,
      child: Container(
        padding: const EdgeInsets.symmetric(horizontal: 14, vertical: 6),
        decoration: BoxDecoration(
          color: on ? AppColors.brand : AppColors.surface,
          borderRadius: BorderRadius.circular(999),
          border: Border.all(color: on ? AppColors.brand : AppColors.line2),
        ),
        child: Text(label, style: TextStyle(
          fontFamily: 'PlusJakartaSans', fontWeight: FontWeight.w600, fontSize: 12.5,
          color: on ? Colors.white : AppColors.text2,
        )),
      ),
    );
  }
}

class _Row extends StatelessWidget {
  const _Row({required this.c, required this.now, required this.onTap});
  final InboxConversation c;
  final DateTime now;
  final VoidCallback onTap;

  @override
  Widget build(BuildContext context) {
    final unread = c.unread > 0;
    return Material(
      color: unread ? AppColors.brand50.withValues(alpha: 0.45) : AppColors.surface,
      child: InkWell(
        onTap: onTap,
        child: Padding(
          padding: const EdgeInsets.symmetric(horizontal: 16, vertical: 12),
          child: Row(crossAxisAlignment: CrossAxisAlignment.start, children: [
            BrutalAvatar(name: c.leadName, size: 42),
            const SizedBox(width: 12),
            Expanded(
              child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
                Row(children: [
                  Expanded(
                    child: Text(c.leadName, maxLines: 1, overflow: TextOverflow.ellipsis,
                        style: TextStyle(fontFamily: 'PlusJakartaSans', fontSize: 14.5,
                            fontWeight: unread ? FontWeight.w800 : FontWeight.w600, color: AppColors.text)),
                  ),
                  Text(inboxListTime(c.lastAt, now), style: TextStyle(
                    fontSize: 11.5, color: unread ? AppColors.won : AppColors.text3,
                    fontWeight: unread ? FontWeight.w700 : FontWeight.w400,
                  )),
                ]),
                const SizedBox(height: 3),
                Row(children: [
                  if (c.lastIsMine)
                    Padding(
                      padding: const EdgeInsets.only(right: 4),
                      child: Icon(c.lastStatus == 'failed' ? Icons.error_outline : Icons.done_all,
                          size: 14, color: c.lastStatus == 'read' ? AppColors.brass
                              : c.lastStatus == 'failed' ? AppColors.hot : AppColors.text3),
                    ),
                  Expanded(
                    child: Text(c.lastText.isEmpty ? '…' : c.lastText, maxLines: 1, overflow: TextOverflow.ellipsis,
                        style: TextStyle(fontSize: 13, color: unread ? AppColors.text : AppColors.text2)),
                  ),
                  if (unread)
                    Container(
                      margin: const EdgeInsets.only(left: 6),
                      padding: const EdgeInsets.symmetric(horizontal: 6, vertical: 1),
                      constraints: const BoxConstraints(minWidth: 20),
                      decoration: BoxDecoration(color: AppColors.won, borderRadius: BorderRadius.circular(999)),
                      child: Text(c.unread > 99 ? '99+' : '${c.unread}', textAlign: TextAlign.center,
                          style: const TextStyle(color: Colors.white, fontSize: 11, fontWeight: FontWeight.w700)),
                    ),
                ]),
                if (!c.window.open) ...[
                  const SizedBox(height: 3),
                  const Text('24h window closed — template only',
                      style: TextStyle(fontSize: 11, color: AppColors.text3)),
                ],
              ]),
            ),
          ]),
        ),
      ),
    );
  }
}
