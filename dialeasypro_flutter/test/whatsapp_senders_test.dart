import 'package:dialeasypro/data/models/models.dart';
import 'package:flutter_test/flutter_test.dart';

void main() {
  test('a sender is read from /comms/whatsapp/senders/', () {
    final s = WhatsAppSender.fromJson({
      'id': 3, 'label': 'Support', 'display_phone': '+91 98765 11111',
      'is_default': false, 'is_active': true, 'provider': 'meta_cloud',
    });
    expect(s.id, 3);
    expect(s.title, 'Support (+91 98765 11111)');
    expect(s.isActive, isTrue);
    expect(const WhatsAppSender(id: 1, label: 'Sales').title, 'Sales');
  });

  test('a template knows the number it was approved on', () {
    final t = WhatsAppTemplate.fromJson({
      'id': 9, 'name': 'welcome', 'body_text': 'Hi {{1}}', 'account': 3, 'account_label': 'Support',
    });
    expect(t.accountId, 3);
    expect(t.accountLabel, 'Support');
    final shared = WhatsAppTemplate.fromJson({'id': 10, 'name': 'x', 'body_text': 'y', 'account': null});
    expect(shared.accountId, isNull);
    expect(shared.accountLabel, '');
  });
}
