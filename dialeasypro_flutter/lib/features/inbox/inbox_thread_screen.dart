// ============================================================
// DialSathi — One WhatsApp conversation
//
// The chat with a lead and a reply box. Free text goes out from the number
// the customer wrote to (the server picks it); it is offered only inside
// WhatsApp's 24-hour window. Outside it, or whenever the agent wants one,
// the template screen opens — it already knows variables and "Send from".
//
// Opening the conversation marks it read for the whole team.
// ============================================================
import 'dart:async';

import 'package:flutter/material.dart';
import 'package:go_router/go_router.dart';

import '../../core/services/whatsapp_service.dart';
import '../../core/theme/colors.dart';
import '../../data/models/models.dart';
import '../../data/services/services.dart';

/// "Today", "Yesterday" or "Mon, 21 Nov".
String inboxDayLabel(DateTime at, DateTime now) {
  final today = DateTime(now.year, now.month, now.day);
  final day = DateTime(at.year, at.month, at.day);
  final diff = today.difference(day).inDays;
  if (diff == 0) return 'Today';
  if (diff == 1) return 'Yesterday';
  const days = ['Mon', 'Tue', 'Wed', 'Thu', 'Fri', 'Sat', 'Sun'];
  const months = ['Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun', 'Jul', 'Aug', 'Sep', 'Oct', 'Nov', 'Dec'];
  return '${days[at.weekday - 1]}, ${at.day} ${months[at.month - 1]}';
}

String _clock(DateTime at) {
  final h = at.hour % 12 == 0 ? 12 : at.hour % 12;
  return '$h:${at.minute.toString().padLeft(2, '0')} ${at.hour < 12 ? 'am' : 'pm'}';
}

class InboxThreadScreen extends StatefulWidget {
  const InboxThreadScreen({super.key, required this.leadId});
  final int leadId;

  @override
  State<InboxThreadScreen> createState() => _InboxThreadScreenState();
}

class _InboxThreadScreenState extends State<InboxThreadScreen> with WidgetsBindingObserver {
  InboxThread? _thread;
  String? _error;
  bool _sending = false;
  Timer? _poll;
  final _text = TextEditingController();

  @override
  void initState() {
    super.initState();
    WidgetsBinding.instance.addObserver(this);
    _load();
    _poll = Timer.periodic(const Duration(seconds: 20), (_) => _load());
  }

  @override
  void dispose() {
    WidgetsBinding.instance.removeObserver(this);
    _poll?.cancel();
    _text.dispose();
    super.dispose();
  }

  @override
  void didChangeAppLifecycleState(AppLifecycleState state) {
    if (state == AppLifecycleState.resumed) _load();
  }

  Future<void> _load() async {
    try {
      final t = await InboxService.instance.thread(widget.leadId);
      if (!mounted) return;
      setState(() {
        _thread = t;
        _error = null;
      });
      // On screen = read, for everyone.
      if (t.unread > 0) {
        InboxService.instance.markRead(widget.leadId).catchError((_) {});
      }
    } catch (_) {
      if (!mounted) return;
      if (_thread == null) setState(() => _error = 'Could not open this conversation.');
    }
  }

  Future<void> _send() async {
    final message = _text.text.trim();
    if (message.isEmpty || _sending) return;
    setState(() => _sending = true);
    final err = await WhatsAppService.instance.sendCloud(leadId: widget.leadId, message: message);
    if (!mounted) return;
    setState(() => _sending = false);
    if (err != null) {
      ScaffoldMessenger.of(context).showSnackBar(SnackBar(content: Text(err)));
      return;
    }
    _text.clear();
    // Queued on the server; look again once it has gone out.
    for (final ms in [1500, 5000]) {
      Future.delayed(Duration(milliseconds: ms), () => mounted ? _load() : null);
    }
  }

  Future<void> _sendTemplate() async {
    await context.push('/leads/${widget.leadId}/whatsapp');
    _load();
  }

  @override
  Widget build(BuildContext context) {
    final t = _thread;
    return Scaffold(
      backgroundColor: AppColors.surface2,
      appBar: AppBar(
        titleSpacing: 0,
        title: t == null
            ? const Text('Conversation')
            : Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
                Text(t.leadName, maxLines: 1, overflow: TextOverflow.ellipsis,
                    style: const TextStyle(fontFamily: 'PlusJakartaSans', fontWeight: FontWeight.w700, fontSize: 16)),
                Text(
                  [t.phone, if (t.lastAccountLabel != null) 'on ${t.lastAccountLabel}'].join(' · '),
                  style: const TextStyle(fontSize: 11.5, color: AppColors.text3),
                ),
              ]),
        actions: [
          IconButton(
            icon: const Icon(Icons.person_outline, color: AppColors.black),
            tooltip: 'Open lead',
            onPressed: () => context.push('/leads/${widget.leadId}'),
          ),
        ],
      ),
      body: Column(children: [
        Expanded(child: _messages(t)),
        if (t != null) _composer(t),
      ]),
    );
  }

  Widget _messages(InboxThread? t) {
    if (t == null) {
      return Center(
        child: _error == null
            ? const CircularProgressIndicator()
            : Text(_error!, style: const TextStyle(color: AppColors.text2)),
      );
    }
    if (t.messages.isEmpty) {
      return const Center(child: Text('No messages yet.', style: TextStyle(color: AppColors.text2)));
    }
    final now = DateTime.now();
    final msgs = t.messages;
    // Newest at the bottom, list anchored there.
    return ListView.builder(
      reverse: true,
      padding: const EdgeInsets.fromLTRB(12, 12, 12, 8),
      itemCount: msgs.length,
      itemBuilder: (_, i) {
        final idx = msgs.length - 1 - i;
        final m = msgs[idx];
        final prev = idx > 0 ? msgs[idx - 1] : null;
        final newDay = prev == null ||
            DateTime(prev.at.year, prev.at.month, prev.at.day) != DateTime(m.at.year, m.at.month, m.at.day);
        return Column(children: [
          if (newDay)
            Padding(
              padding: const EdgeInsets.symmetric(vertical: 8),
              child: Container(
                padding: const EdgeInsets.symmetric(horizontal: 10, vertical: 3),
                decoration: BoxDecoration(color: AppColors.sunken, borderRadius: BorderRadius.circular(999)),
                child: Text(inboxDayLabel(m.at, now),
                    style: const TextStyle(fontSize: 11, fontWeight: FontWeight.w600, color: AppColors.text2)),
              ),
            ),
          _Bubble(m: m),
        ]);
      },
    );
  }

  Widget _composer(InboxThread t) {
    final left = t.window.leftLabel(DateTime.now());
    return SafeArea(
      top: false,
      child: Container(
        padding: const EdgeInsets.fromLTRB(10, 8, 10, 8),
        decoration: const BoxDecoration(
          color: AppColors.surface,
          border: Border(top: BorderSide(color: AppColors.line)),
        ),
        child: t.window.open
            ? Column(mainAxisSize: MainAxisSize.min, children: [
                Row(crossAxisAlignment: CrossAxisAlignment.end, children: [
                  IconButton(
                    icon: const Icon(Icons.description_outlined, color: AppColors.text2),
                    tooltip: 'Send a template',
                    onPressed: _sendTemplate,
                  ),
                  Expanded(
                    child: TextField(
                      controller: _text,
                      minLines: 1,
                      maxLines: 5,
                      maxLength: 4096,
                      textCapitalization: TextCapitalization.sentences,
                      decoration: InputDecoration(
                        hintText: 'Type a reply',
                        counterText: '',
                        isDense: true,
                        filled: true,
                        fillColor: AppColors.surface2,
                        contentPadding: const EdgeInsets.symmetric(horizontal: 14, vertical: 10),
                        border: OutlineInputBorder(borderRadius: BorderRadius.circular(22),
                            borderSide: const BorderSide(color: AppColors.line2)),
                      ),
                    ),
                  ),
                  const SizedBox(width: 6),
                  IconButton.filled(
                    style: IconButton.styleFrom(backgroundColor: AppColors.brand),
                    icon: _sending
                        ? const SizedBox(width: 18, height: 18,
                            child: CircularProgressIndicator(strokeWidth: 2, color: Colors.white))
                        : const Icon(Icons.send, color: Colors.white, size: 20),
                    tooltip: 'Send',
                    onPressed: _sending ? null : _send,
                  ),
                ]),
                if (left.isNotEmpty)
                  Padding(
                    padding: const EdgeInsets.only(top: 2),
                    child: Text('Reply window: $left',
                        style: const TextStyle(fontSize: 10.5, color: AppColors.text3)),
                  ),
              ])
            : Column(mainAxisSize: MainAxisSize.min, crossAxisAlignment: CrossAxisAlignment.stretch, children: [
                Container(
                  padding: const EdgeInsets.all(10),
                  decoration: BoxDecoration(color: AppColors.warmBg, borderRadius: BorderRadius.circular(10)),
                  child: const Text(
                    'The customer last wrote more than 24 hours ago, so WhatsApp only allows an approved '
                    'template now. Once they reply you can type freely again.',
                    style: TextStyle(fontSize: 12.5, color: AppColors.text),
                  ),
                ),
                const SizedBox(height: 8),
                FilledButton.icon(
                  style: FilledButton.styleFrom(backgroundColor: AppColors.brand),
                  icon: const Icon(Icons.description_outlined),
                  label: const Text('Send a template'),
                  onPressed: _sendTemplate,
                ),
              ]),
      ),
    );
  }
}

class _Bubble extends StatelessWidget {
  const _Bubble({required this.m});
  final InboxMessage m;

  @override
  Widget build(BuildContext context) {
    final mine = m.isMine;
    final failed = m.status == 'failed';
    return Align(
      alignment: mine ? Alignment.centerRight : Alignment.centerLeft,
      child: Container(
        margin: const EdgeInsets.symmetric(vertical: 3),
        constraints: BoxConstraints(maxWidth: MediaQuery.of(context).size.width * 0.78),
        padding: const EdgeInsets.fromLTRB(12, 8, 12, 6),
        decoration: BoxDecoration(
          color: mine ? AppColors.wonBg : AppColors.surface,
          border: Border.all(color: failed ? AppColors.hot : AppColors.line),
          borderRadius: BorderRadius.only(
            topLeft: Radius.circular(mine ? 14 : 4),
            topRight: Radius.circular(mine ? 4 : 14),
            bottomLeft: const Radius.circular(14),
            bottomRight: const Radius.circular(14),
          ),
        ),
        child: Column(
          crossAxisAlignment: mine ? CrossAxisAlignment.end : CrossAxisAlignment.start,
          children: [
            if ((m.templateName ?? '').isNotEmpty && m.content.isNotEmpty)
              Text('TEMPLATE · ${m.templateName!.toUpperCase()}',
                  style: const TextStyle(fontSize: 9.5, fontWeight: FontWeight.w700, color: AppColors.text3, letterSpacing: .3)),
            Text(m.display, style: const TextStyle(fontSize: 14, color: AppColors.text, height: 1.35)),
            const SizedBox(height: 3),
            Row(mainAxisSize: MainAxisSize.min, children: [
              Text(
                [
                  if (mine) m.sentByName ?? 'System',
                  _clock(m.at),
                ].join(' · '),
                style: const TextStyle(fontSize: 10.5, color: AppColors.text3),
              ),
              if (mine) ...[
                const SizedBox(width: 4),
                Icon(
                  failed ? Icons.error_outline : m.status == 'queued' ? Icons.schedule
                      : m.status == 'sent' ? Icons.done : Icons.done_all,
                  size: 13,
                  color: failed ? AppColors.hot : m.status == 'read' ? AppColors.brass : AppColors.text3,
                ),
              ],
            ]),
            if (failed && m.errorMessage.isNotEmpty)
              Padding(
                padding: const EdgeInsets.only(top: 2),
                child: Text(m.errorMessage, style: const TextStyle(fontSize: 11, color: AppColors.hot)),
              ),
          ],
        ),
      ),
    );
  }
}
