// "Save & break": save the call, but leave the queue paused on the next lead
// instead of dialling it. Before this an agent in a queue could only break
// between calls — and between calls the next one was already being dialled —
// so they had to finish the whole queue first.

import 'dart:convert';

import 'package:dio/dio.dart';
import 'package:flutter/services.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:shared_preferences/shared_preferences.dart';

import 'package:dialeasypro/data/models/models.dart';
import 'package:dialeasypro/data/services/api_client.dart';
import 'package:dialeasypro/features/dialer/dialer_state.dart';

/// Answers every request as the API would a saved call.
class _SavedCall implements HttpClientAdapter {
  final List<String> paths = [];

  @override
  Future<ResponseBody> fetch(RequestOptions options, Stream<Uint8List>? body, Future<void>? cancel) async {
    paths.add(options.path);
    return ResponseBody.fromString(
      jsonEncode({'id': 'call-1', 'phone_number': '+919812300001', 'started_at': '2026-10-09T10:00:00Z'}),
      201,
      headers: {Headers.contentTypeHeader: [Headers.jsonContentType]},
    );
  }

  @override
  void close({bool force = false}) {}
}

Lead _lead(int id) => Lead.fromJson({'id': id, 'name': 'Lead $id', 'phone': '+91981230000$id'});

void main() {
  TestWidgetsFlutterBinding.ensureInitialized();
  late _SavedCall server;

  setUpAll(() {
    TestDefaultBinaryMessengerBinding.instance.defaultBinaryMessenger.setMockMethodCallHandler(
      const MethodChannel('com.llfbandit.record/messages'),
      (_) async => null,
    );
  });

  setUp(() {
    SharedPreferences.setMockInitialValues({});
    server = _SavedCall();
    ApiClient.instance.dio.httpClientAdapter = server;
  });

  ProviderContainer queueAfterACall() {
    final container = ProviderContainer();
    addTearDown(container.dispose);
    container.read(dialerProvider.notifier).state = DialerState(
      mode: DialerMode.queue,
      phase: DialerPhase.postCall,
      queue: [_lead(1), _lead(2)],
      currentIndex: 0,
      currentCall: DialerCallRecord(
        leadId: 1, leadName: 'Lead 1', phoneNumber: '+919812300001',
        startedAt: DateTime.now().subtract(const Duration(minutes: 1)),
      )..endedAt = DateTime.now(),
    );
    return container;
  }

  test('Save & break saves the call and holds the queue on the next lead', () async {
    final container = queueAfterACall();
    final dialer = container.read(dialerProvider.notifier);

    final saved = await dialer.dispose_(
      dispositionId: 5, dispositionName: 'Busy', wasConnected: false, holdNext: true,
    );

    expect(saved, isTrue);
    expect(server.paths, contains('/calls/'), reason: 'the call was saved');
    final state = container.read(dialerProvider);
    expect(state.phase, DialerPhase.paused, reason: 'nothing dials while on break');
    expect(state.currentIndex, 1, reason: 'resuming dials the next lead, not this one again');
    expect(state.currentCall, isNull);
    expect(state.completedCalls, hasLength(1));

    // Well past the auto-next delay: still paused, nothing dialled.
    await Future<void>.delayed(const Duration(milliseconds: 2500));
    expect(container.read(dialerProvider).phase, DialerPhase.paused);
  });

  test('Save & next still moves straight on to the next lead', () async {
    final container = queueAfterACall();
    final dialer = container.read(dialerProvider.notifier);

    await dialer.dispose_(dispositionId: 5, dispositionName: 'Busy', wasConnected: false);

    final state = container.read(dialerProvider);
    expect(state.phase, DialerPhase.preCall, reason: 'about to dial the next one');
    expect(state.currentIndex, 1);
    dialer.stop(); // don't let the auto-dial timer place a call in the test
  });
}
