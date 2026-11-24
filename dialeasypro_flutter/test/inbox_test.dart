import 'package:dialeasypro/data/models/models.dart';
import 'package:dialeasypro/features/inbox/inbox_screen.dart';
import 'package:dialeasypro/features/inbox/inbox_thread_screen.dart';
import 'package:flutter_test/flutter_test.dart';

void main() {
  group('ReplyWindow', () {
    final now = DateTime(2026, 11, 23, 10, 0);

    test('shows hours, then minutes, then nothing once closed', () {
      expect(ReplyWindow(open: true, closesAt: now.add(const Duration(hours: 23, minutes: 50))).leftLabel(now), '23h left');
      expect(ReplyWindow(open: true, closesAt: now.add(const Duration(minutes: 40))).leftLabel(now), '40 min left');
      expect(ReplyWindow(open: true, closesAt: now.add(const Duration(seconds: 20))).leftLabel(now), '1 min left');
      expect(ReplyWindow(open: false, closesAt: now.subtract(const Duration(hours: 2))).leftLabel(now), '');
    });
  });

  test('a conversation reads the server row', () {
    final c = InboxConversation.fromJson({
      'lead_id': 5, 'lead_name': 'Ravi', 'phone': '+919812300001', 'status': 'new',
      'owner_name': null, 'unread': 2,
      'last_message': {'text': 'Price?', 'direction': 'inbound', 'status': 'received',
                       'at': '2026-11-23T08:00:00Z', 'account_label': 'Sales'},
      'window': {'open': true, 'closes_at': '2026-11-24T08:00:00Z'},
    });
    expect(c.leadId, 5);
    expect(c.unread, 2);
    expect(c.lastIsMine, isFalse);
    expect(c.lastAccountLabel, 'Sales');
    expect(c.window.open, isTrue);
  });

  test('a template message without text shows the template name', () {
    final m = InboxMessage.fromJson({
      'id': 'x', 'direction': 'outbound', 'message_type': 'template', 'content': '',
      'template_name': 'welcome_lead', 'status': 'delivered', 'created_at': '2026-11-23T08:00:00Z',
    });
    expect(m.display, 'Template: welcome_lead');
    expect(m.isMine, isTrue);
  });

  test('list and day labels', () {
    final now = DateTime(2026, 11, 23, 18, 0);
    expect(inboxListTime(DateTime(2026, 11, 23, 9, 5), now), '9:05 am');
    expect(inboxListTime(DateTime(2026, 11, 22, 21, 0), now), 'Yesterday');
    expect(inboxListTime(DateTime(2026, 11, 2, 9, 0), now), '2 Nov');
    expect(inboxDayLabel(DateTime(2026, 11, 23, 1), now), 'Today');
    expect(inboxDayLabel(DateTime(2026, 11, 22, 1), now), 'Yesterday');
    expect(inboxDayLabel(DateTime(2026, 11, 20, 1), now), 'Fri, 20 Nov');
  });
}
