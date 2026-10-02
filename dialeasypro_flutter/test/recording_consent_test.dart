// Google Play: call audio may only be collected after a prominent in-app
// disclosure the user has agreed to, shown before the permission request.
// Recording is therefore off — whatever the switch says — until the agent has
// agreed, including on installs that had it on before the disclosure existed.

import 'package:flutter/material.dart';
import 'package:flutter/services.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:shared_preferences/shared_preferences.dart';

import 'package:dialeasypro/core/services/call_recording_service.dart';
import 'package:dialeasypro/features/setup/recording_disclosure.dart';

void main() {
  TestWidgetsFlutterBinding.ensureInitialized();

  // CallRecordingService creates the recorder plugin on first use; there is
  // no native side in a unit test.
  setUpAll(() {
    TestDefaultBinaryMessengerBinding.instance.defaultBinaryMessenger.setMockMethodCallHandler(
      const MethodChannel('com.llfbandit.record/messages'),
      (_) async => null,
    );
  });

  // A getter, not a field: the instance must be created after the stub above.
  CallRecordingService service() => CallRecordingService.instance;

  test('recording switched on before the disclosure existed stays off', () async {
    SharedPreferences.setMockInitialValues({'call_recording_enabled': true});

    expect(await service().isEnabled(), isFalse);
  });

  test('it cannot be switched on without consent', () async {
    SharedPreferences.setMockInitialValues({});

    await service().setEnabled(true);

    expect(await service().isEnabled(), isFalse);
    final prefs = await SharedPreferences.getInstance();
    expect(prefs.getBool('call_recording_enabled'), isNull);
  });

  test('after agreeing it switches on and off normally', () async {
    SharedPreferences.setMockInitialValues({});

    await service().recordConsent();
    await service().setEnabled(true);
    expect(await service().isEnabled(), isTrue);

    await service().setEnabled(false);
    expect(await service().isEnabled(), isFalse);
  });

  Future<bool?> openDisclosure(WidgetTester tester) async {
    bool? result;
    await tester.pumpWidget(MaterialApp(
      home: Builder(builder: (context) => TextButton(
        onPressed: () async => result = await confirmRecordingDisclosure(context),
        child: const Text('enable'),
      )),
    ));
    await tester.tap(find.text('enable'));
    await tester.pumpAndSettle();
    return result;
  }

  testWidgets('declining records no consent', (tester) async {
    SharedPreferences.setMockInitialValues({});
    await openDisclosure(tester);

    expect(find.text('What is collected'), findsOneWidget);
    await tester.tap(find.text('Not now'));
    await tester.pumpAndSettle();

    expect(await service().hasConsent(), isFalse);
  });

  testWidgets('agreeing records consent, and the dialog is not shown again', (tester) async {
    SharedPreferences.setMockInitialValues({});
    await openDisclosure(tester);
    await tester.tap(find.text('I agree'));
    await tester.pumpAndSettle();
    expect(await service().hasConsent(), isTrue);

    await tester.tap(find.text('enable'));
    await tester.pumpAndSettle();
    expect(find.text('What is collected'), findsNothing);
  });
}
