// The call outcome is picked from one dropdown. It used to be a chip per
// disposition, which filled the screen for a tenant with many of them and
// pushed the notes and the save button out of sight.

import 'package:flutter/material.dart';
import 'package:flutter/services.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:shared_preferences/shared_preferences.dart';

import 'package:dialeasypro/data/models/models.dart';
import 'package:dialeasypro/features/dialer/dialer_screen.dart';
import 'package:dialeasypro/features/dialer/dialer_state.dart';

const outcomes = [
  CallDisposition(id: 1, name: 'Interested', slug: 'interested', isPositive: true),
  CallDisposition(id: 2, name: 'Call back later', slug: 'call-back', autoFollowupHours: 24),
  CallDisposition(id: 3, name: 'Not interested', slug: 'not-interested'),
  CallDisposition(id: 4, name: 'Wrong number', slug: 'wrong-number'),
  CallDisposition(id: 5, name: 'Switched off', slug: 'switched-off'),
  CallDisposition(id: 6, name: 'Busy', slug: 'busy'),
  CallDisposition(id: 7, name: 'Site visit booked', slug: 'site-visit', isPositive: true),
];

Future<void> pumpOutcomeScreen(WidgetTester tester) async {
  final container = ProviderContainer(overrides: [
    dispositionsProvider.overrideWith((_) async => outcomes),
  ]);
  addTearDown(container.dispose);
  container.read(dialerProvider.notifier).state = DialerState(
    mode: DialerMode.single,
    phase: DialerPhase.postCall,
    queue: [Lead.fromJson({'id': 1, 'name': 'Rahul Sharma', 'phone': '+919812300001'})],
    currentCall: DialerCallRecord(
      leadId: 1, leadName: 'Rahul Sharma', phoneNumber: '+919812300001',
      startedAt: DateTime.now().subtract(const Duration(minutes: 2)),
    ),
  );
  await tester.pumpWidget(UncontrolledProviderScope(
    container: container,
    child: const MaterialApp(home: DialerScreen()),
  ));
  await tester.pump();
  await tester.pump(const Duration(milliseconds: 100));
}

void main() {
  TestWidgetsFlutterBinding.ensureInitialized();

  setUpAll(() {
    TestDefaultBinaryMessengerBinding.instance.defaultBinaryMessenger.setMockMethodCallHandler(
      const MethodChannel('com.llfbandit.record/messages'),
      (_) async => null,
    );
  });
  setUp(() => SharedPreferences.setMockInitialValues({}));

  testWidgets('outcomes are one dropdown, not a chip each', (tester) async {
    await pumpOutcomeScreen(tester);

    expect(find.byType(DropdownButtonFormField<int>), findsOneWidget);
    expect(find.text('Choose the call outcome'), findsOneWidget);
    // Nothing listed on the screen itself until the dropdown is opened.
    expect(find.text('Site visit booked'), findsNothing);
  });

  testWidgets('picking an outcome selects it and says when it books a follow-up', (tester) async {
    await pumpOutcomeScreen(tester);

    await tester.tap(find.byType(DropdownButtonFormField<int>));
    await tester.pumpAndSettle();
    await tester.tap(find.text('Call back later').last);
    await tester.pumpAndSettle();

    expect(find.text('Call back later'), findsOneWidget);
    expect(find.textContaining('follow-up is scheduled automatically in 24 h'), findsOneWidget);
  });
}
