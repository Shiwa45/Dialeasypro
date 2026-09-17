// Custom fields on a lead.
//
// The server has always sent `custom_field_values` on the lead detail and on
// the dialer's queue pull. The app's Lead model never parsed it, so every
// custom field — imported from CSV, set on the web — was dropped before any
// screen could show it, including to an agent mid-call.
//
// The payloads below are the real shape from LeadDetailSerializer, copied from
// the running API.
import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';

import 'package:dialeasypro/data/models/models.dart';
import 'package:dialeasypro/features/leads/lead_custom_fields.dart';

Map<String, dynamic> _lead({Object? customFields = _absent}) => {
      'id': 54,
      'name': 'Sunita Kapoor',
      'phone': '+919830000054',
      'status': 'interested',
      'created_at': '2026-09-01T10:00:00+05:30',
      if (!identical(customFields, _absent)) 'custom_field_values': customFields,
    };

const _absent = Object();

const _detail = [
  {'field': 1, 'field_key': 'property_type', 'field_name': 'Property Type', 'value': 'Villa'},
  {'field': 2, 'field_key': 'budget_range', 'field_name': 'Budget Range', 'value': '1-2Cr'},
];

Widget _host(Widget child) => MaterialApp(
      home: Scaffold(body: SingleChildScrollView(child: child)),
    );

void main() {
  group('the model', () {
    test('parses the values the API sends', () {
      final lead = Lead.fromJson(_lead(customFields: _detail));

      expect(lead.customFields, hasLength(2));
      expect(lead.customFields.first.name, 'Property Type');
      expect(lead.customFields.first.value, 'Villa');
      expect(lead.customFields.first.key, 'property_type');
    });

    test('knows it was told, even when there are none', () {
      final lead = Lead.fromJson(_lead(customFields: const []));

      expect(lead.customFieldsLoaded, isTrue);
      expect(lead.customFields, isEmpty);
    });

    test('knows it was NOT told when the key is absent', () {
      // The leads list omits custom fields. A lead from there must not read
      // as "has none" — the dialer queue started from the list is this case.
      final lead = Lead.fromJson(_lead());

      expect(lead.customFieldsLoaded, isFalse);
    });

    test('a numeric value is kept as text rather than crashing the parse', () {
      final lead = Lead.fromJson(_lead(customFields: [
        {'field': 3, 'field_key': 'units', 'field_name': 'Units', 'value': 4},
      ]));

      expect(lead.customFields.single.value, '4');
    });

    test('a malformed entry is skipped, not fatal', () {
      final lead = Lead.fromJson(_lead(customFields: ['not a map', ..._detail]));

      expect(lead.customFields, hasLength(2));
    });
  });

  group('the widget', () {
    testWidgets('shows each answered field', (tester) async {
      await tester.pumpWidget(_host(
        LeadCustomFields(lead: Lead.fromJson(_lead(customFields: _detail))),
      ));

      expect(find.text('Property Type'), findsOneWidget);
      expect(find.text('Villa'), findsOneWidget);
      expect(find.text('Budget Range'), findsOneWidget);
      expect(find.text('1-2Cr'), findsOneWidget);
    });

    testWidgets('skips a field left blank', (tester) async {
      await tester.pumpWidget(_host(
        LeadCustomFields(lead: Lead.fromJson(_lead(customFields: [
          ..._detail,
          {'field': 3, 'field_key': 'locality', 'field_name': 'Preferred Locality', 'value': '   '},
        ]))),
      ));

      expect(find.text('Preferred Locality'), findsNothing,
          reason: '"Locality: —" on a live call is noise');
      expect(find.text('Villa'), findsOneWidget);
    });

    testWidgets('renders nothing at all when there are no answers', (tester) async {
      await tester.pumpWidget(_host(
        LeadCustomFields(lead: Lead.fromJson(_lead(customFields: const []))),
      ));

      expect(find.byIcon(Icons.tune), findsNothing,
          reason: 'no empty "Details" header over nothing');
    });

    testWidgets('moving to another lead shows that lead, not the last one', (tester) async {
      // The dialer reuses the widget as it advances through a queue.
      final first = Lead.fromJson(_lead(customFields: _detail));
      final second = Lead.fromJson({
        ..._lead(customFields: [
          {'field': 1, 'field_key': 'property_type', 'field_name': 'Property Type', 'value': 'Apartment'},
        ]),
        'id': 55,
      });

      await tester.pumpWidget(_host(LeadCustomFields(lead: first)));
      expect(find.text('Villa'), findsOneWidget);

      await tester.pumpWidget(_host(LeadCustomFields(lead: second)));
      expect(find.text('Villa'), findsNothing);
      expect(find.text('Apartment'), findsOneWidget);
    });

    testWidgets('a long field name wraps instead of overflowing', (tester) async {
      await tester.pumpWidget(MaterialApp(
        home: Scaffold(
          body: SizedBox(
            width: 300,
            child: LeadCustomFields(
              compact: true,
              lead: Lead.fromJson(_lead(customFields: [
                {
                  'field': 9, 'field_key': 'x',
                  'field_name': 'Expected possession timeline and financing preference',
                  'value': 'Within six months, home loan pre-approved',
                },
              ])),
            ),
          ),
        ),
      ));

      expect(tester.takeException(), isNull);
    });
  });
}
