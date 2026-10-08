// The call outcome is picked from one dropdown. It used to be a chip per
// disposition, which filled the screen for a tenant with many of them and
// pushed the notes and the save button out of sight.
//
// The agent first says whether the call was answered; only the outcomes for
// that kind of call are offered (an unanswered call could be saved as
// "Interested" before, and the server counted it as answered).

import 'package:flutter/material.dart';
import 'package:flutter/services.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:shared_preferences/shared_preferences.dart';

import 'package:dialeasypro/data/models/models.dart';
import 'package:dialeasypro/features/dialer/dialer_screen.dart';
import 'package:dialeasypro/features/dialer/dialer_state.dart';

const outcomes = [
  CallDisposition(id: 1, name: 'Interested', slug: 'interested', isPositive: true, leadStatus: 'interested'),
  CallDisposition(id: 2, name: 'Call back later', slug: 'call-back', autoFollowupHours: 24),
  CallDisposition(id: 3, name: 'Not interested', slug: 'not-interested'),
  CallDisposition(id: 4, name: 'Wrong number', slug: 'wrong-number'),
  CallDisposition(id: 5, name: 'Switched off', slug: 'switched-off', category: 'not_connected'),
  CallDisposition(id: 6, name: 'Busy', slug: 'busy', category: 'not_connected'),
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

  testWidgets('the agent says whether it was answered before any outcome is offered', (tester) async {
    await pumpOutcomeScreen(tester);

    expect(find.byType(DropdownButtonFormField<int>), findsNothing);
    expect(find.text('Choose Answered or Not answered first.'), findsOneWidget);
  });

  testWidgets('outcomes are one dropdown, not a chip each', (tester) async {
    await pumpOutcomeScreen(tester);
    await tester.tap(find.text('✓ Answered'));
    await tester.pumpAndSettle();

    expect(find.byType(DropdownButtonFormField<int>), findsOneWidget);
    expect(find.text('Choose the call outcome'), findsOneWidget);
    // Nothing listed on the screen itself until the dropdown is opened.
    expect(find.text('Site visit booked'), findsNothing);
  });

  testWidgets('an answered call is offered only answered-call outcomes', (tester) async {
    await pumpOutcomeScreen(tester);
    await tester.tap(find.text('✓ Answered'));
    await tester.pumpAndSettle();

    await tester.tap(find.byType(DropdownButtonFormField<int>));
    await tester.pumpAndSettle();

    expect(find.text('Interested'), findsWidgets);
    expect(find.text('Busy'), findsNothing);
    expect(find.text('Switched off'), findsNothing);
  });

  testWidgets('an unanswered call is offered only unanswered-call outcomes', (tester) async {
    await pumpOutcomeScreen(tester);
    await tester.tap(find.text('✕ Not answered'));
    await tester.pumpAndSettle();

    await tester.tap(find.byType(DropdownButtonFormField<int>));
    await tester.pumpAndSettle();

    expect(find.text('Busy'), findsWidgets);
    expect(find.text('Interested'), findsNothing);
  });

  testWidgets('picking an outcome selects it and says what it does', (tester) async {
    await pumpOutcomeScreen(tester);
    await tester.tap(find.text('✓ Answered'));
    await tester.pumpAndSettle();

    await tester.tap(find.byType(DropdownButtonFormField<int>));
    await tester.pumpAndSettle();
    await tester.tap(find.text('Call back later').last);
    await tester.pumpAndSettle();

    expect(find.text('Call back later'), findsOneWidget);
    expect(find.textContaining('follow-up in 24 h'), findsOneWidget);
  });
}
