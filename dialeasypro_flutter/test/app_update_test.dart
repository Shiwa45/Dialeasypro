// The September app update: the break gate, the per-client lead form, and
// the lead basics on the dialing screens.

import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';

import 'package:dialeasypro/data/models/models.dart';
import 'package:dialeasypro/features/dialer/lead_basics_card.dart';
import 'package:dialeasypro/features/work/work_session.dart';

void main() {
  group('while working (not on break)', () {
    test('auto-dialling, the dialer and profile stay open', () {
      for (final path in ['/auto-dial', '/dialer', '/dialer/queue', '/profile', '/notifications']) {
        expect(allowedWhileWorking(path), isTrue, reason: path);
      }
    });

    test('leads, manual calls, WhatsApp and the other tabs need a break', () {
      for (final path in ['/dashboard', '/leads', '/leads/12', '/leads/12/whatsapp', '/calls', '/reports', '/my-work']) {
        expect(allowedWhileWorking(path), isFalse, reason: path);
      }
    });

    test('a path that merely starts the same is not let through', () {
      expect(allowedWhileWorking('/dialerx'), isFalse);
    });
  });

  group('the client lead form', () {
    test('an older server with no config gives the plain form', () {
      const config = LeadFormConfig();
      expect(config.budget.show, isTrue);
      expect(config.dealValue.label, 'Deal Value (₹)');
      expect(config.customFields, isEmpty);
    });

    test('money fields can be hidden and renamed per client', () {
      final config = LeadFormConfig.fromJson({
        'standard': {
          'budget': {'show': true, 'label': 'Order Value'},
          'deal_value': {'show': false, 'label': ''},
        },
        'custom_fields': [
          {'field_key': 'property_type', 'name': 'Property Type', 'field_type': 'dropdown',
           'options': ['1BHK', '2BHK'], 'is_required': true},
        ],
      });

      expect(config.budget.label, 'Order Value');
      expect(config.dealValue.show, isFalse);
      expect(config.dealValue.label, 'Deal Value (₹)', reason: 'blank label falls back');
      final field = config.customFields.single;
      expect(field.type, 'dropdown');
      expect(field.options, ['1BHK', '2BHK']);
      expect(field.required, isTrue);
    });
  });

  group('lead basics on the dialing screen', () {
    Lead lead(Map<String, dynamic> extra) => Lead.fromJson({
          'id': 1, 'name': 'Ravi', 'phone': '+919812300001', ...extra,
        });

    Future<void> pump(WidgetTester tester, Lead l) => tester.pumpWidget(MaterialApp(
          home: Scaffold(body: SingleChildScrollView(child: LeadBasicsCard(lead: l))),
        ));

    testWidgets('shows what is known', (tester) async {
      await pump(tester, lead({
        'source_display': 'IndiaMART', 'budget': '5000000', 'email': 'ravi@example.com',
        'dial_attempts': 3, 'connected_calls': 1,
        'last_call_connected': true, 'last_disposition_name': 'Call back later',
      }));

      expect(find.text('IndiaMART'), findsOneWidget);
      expect(find.text('₹50.0L'), findsOneWidget);
      expect(find.text('ravi@example.com'), findsOneWidget);
      expect(find.text('3× · 1 answered'), findsOneWidget);
      expect(find.text('Answered · Call back later'), findsOneWidget, reason: 'how the last call went');
    });

    testWidgets('leaves out what is empty', (tester) async {
      await pump(tester, lead({'source_display': ''}));

      expect(find.text('Budget'), findsNothing);
      expect(find.text('Email'), findsNothing);
      expect(find.text('Never'), findsOneWidget, reason: 'call count always shows');
    });
  });
}
