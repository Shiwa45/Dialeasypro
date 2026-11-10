import 'package:dialeasypro/core/services/call_recording_service.dart';
import 'package:dialeasypro/core/services/call_tracking_service.dart';
import 'package:flutter/services.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:shared_preferences/shared_preferences.dart';

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

  group('call-log entries sent to the server', () {
    test('an entry becomes the sync payload', () {
      final p = syncPayloadFor({
        'id': '881', 'number': '+91 98123 00001', 'type': 'outgoing',
        'dateMillis': 1762671600000, 'durationSec': 42, 'cachedName': 'Ravi',
      });
      expect(p, {
        'device_id': '881', 'number': '+91 98123 00001', 'type': 'outgoing',
        'started_at': 1762671600000, 'duration_seconds': 42,
      });
    });

    test('private and withheld numbers are not sent', () {
      expect(syncPayloadFor({'id': '1', 'number': '', 'type': 'incoming', 'dateMillis': 1}), isNull);
      expect(syncPayloadFor({'id': '1', 'number': '-2', 'type': 'incoming', 'dateMillis': 1}), isNull);
      expect(syncPayloadFor({'id': '1', 'number': '121', 'type': 'incoming', 'dateMillis': 1}), isNull);
    });

    test('an entry without an id, type or time is not sent', () {
      expect(syncPayloadFor({'number': '9812300001', 'type': 'incoming', 'dateMillis': 1}), isNull);
      expect(syncPayloadFor({'id': '1', 'number': '9812300001', 'dateMillis': 1}), isNull);
      expect(syncPayloadFor({'id': '1', 'number': '9812300001', 'type': 'incoming'}), isNull);
    });

    test('the next sync starts at the newest entry sent', () {
      expect(nextWatermark(100, [
        {'dateMillis': 150}, {'dateMillis': 400}, {'dateMillis': 220},
      ]), 400);
      expect(nextWatermark(500, const []), 500);
      expect(nextWatermark(500, [{'dateMillis': 300}]), 500);
    });
  });

  group('what the agent must allow', () {
    CallTrackingReadiness r({
      bool supported = true, bool callLog = true, bool phone = true,
      bool storage = true, bool recording = true, bool googleDialer = false,
    }) =>
        CallTrackingReadiness(
          callLogSupported: supported, callLog: callLog, phone: phone,
          storage: storage, recording: recording, battery: false, googleDialer: googleDialer,
        );

    test('complete only with call log, phone, files and recording', () {
      expect(r().complete, isTrue);
      expect(r(callLog: false).complete, isFalse);
      expect(r(phone: false).complete, isFalse);
      expect(r(storage: false).complete, isFalse);
      expect(r(recording: false).complete, isFalse);
    });

    test('the Google Phone app must be replaced as the default dialer', () {
      expect(r(googleDialer: true).complete, isFalse);
    });

    test('a build that cannot read the call log does not lock the agent out', () {
      expect(r(supported: false, googleDialer: true).complete, isTrue);
      expect(r(supported: false, callLog: false).complete, isTrue);
    });
  });

  group('finding recordings on any brand', () {
    final end = DateTime(2026, 11, 9, 14, 32, 5);
    const phone = '+919812300001';

    ({int score, String matchedBy})? match(String name, {String who = '', int lateSec = 4}) =>
        scoreRecordingCandidate(
          fileName: name,
          modified: end.add(Duration(seconds: lateSec)),
          phoneNumber: phone,
          callEnd: end,
          leadName: who,
        );

    // Names real recorders write, by brand.
    final named = {
      'Samsung (One UI)': 'Call recording 9812300001_261109_143205.m4a',
      'Samsung, older': '+91 98123 00001_261109_143205.m4a',
      'Xiaomi (MIUI)': '9812300001(9812300001)_20261109143205.mp3',
      'Vivo / iQOO': '9812300001 2026-11-09 14-32-05.m4a',
      'Oppo / Realme / OnePlus': 'PhoneRecord_919812300001_20261109143205.m4a',
      'Honor / Huawei': '919812300001_20261109143205.amr',
      'Infinix / Tecno': 'CallRecord_+919812300001_20261109_143205.aac',
    };
    named.forEach((brand, file) {
      test('$brand: "$file" is matched by number', () {
        expect(match(file)?.matchedBy, 'filename_number');
      });
    });

    test('a file named after the phone contact matches through the call-log name', () {
      // The contact is saved as "Ravi Sir"; the lead is "Ravi Kumar". Written
      // two minutes after the call, so timing alone can't match it.
      expect(match('Ravi Sir_261109_143205.m4a', who: 'Ravi Kumar', lateSec: 120), isNull);
      expect(match('Ravi Sir_261109_143205.m4a', who: 'Ravi Sir', lateSec: 120)?.matchedBy, 'filename_name');
    });

    test('the Google Phone app is recognised (its recordings are private)', () {
      expect(isGoogleDialer('com.google.android.dialer'), isTrue);
      expect(isGoogleDialer('com.samsung.android.dialer'), isFalse);
      expect(isGoogleDialer('com.android.incallui'), isFalse);
      expect(isGoogleDialer(''), isFalse);
    });

    test('only call-recorder folders are trusted for a time-only match', () {
      expect(looksLikeCallRecordingFolder('Recordings/Call/rec.m4a'), isTrue);
      expect(looksLikeCallRecordingFolder('Recordings/Record/Call/x.m4a'), isTrue);
      expect(looksLikeCallRecordingFolder('MIUI/sound_recorder/call_rec/x.mp3'), isTrue);
      expect(looksLikeCallRecordingFolder('Music/Recordings/PhoneRecord/x.m4a'), isTrue);
      expect(looksLikeCallRecordingFolder('Recordings/Voice Recorder/Call me.m4a'), isFalse);
      expect(looksLikeCallRecordingFolder('Music/WhatsApp Audio/x.opus'), isFalse);
      expect(looksLikeCallRecordingFolder('Download/song.mp3'), isFalse);
    });
  });

  group('recording source (built-in recorder / recorder app / microphone)', () {
    setUp(() => SharedPreferences.setMockInitialValues({}));

    test('the built-in recorder is the default', () async {
      expect(await CallRecordingService.instance.recordingSource(), 'builtin');
    });

    test('a recorder app keeps the microphone off; the app microphone turns it on', () async {
      final svc = CallRecordingService.instance;
      await svc.setRecordingSource('recorder_app');
      expect(await svc.micMode(), 'never');
      expect(await svc.shouldUseMicFallback(), isFalse);
      await svc.setRecordingSource('app_mic');
      expect(await svc.micMode(), 'always');
      expect(await svc.shouldUseMicFallback(), isTrue);
      await svc.setRecordingSource('builtin');
      expect(await svc.micMode(), 'auto');
    });

    test('an unknown source is ignored', () async {
      await CallRecordingService.instance.setRecordingSource('cloud');
      expect(await CallRecordingService.instance.recordingSource(), 'builtin');
    });

    test('one file is the same file however it was found', () {
      final t = DateTime(2026, 11, 9, 14, 32, 5, 400);
      expect(recordingIdentity('Call 9812300001.m4a', 52000, t),
          recordingIdentity('call 9812300001.M4A', 52000, DateTime(2026, 11, 9, 14, 32, 5, 900)));
      expect(recordingIdentity('a.m4a', 52000, t), isNot(recordingIdentity('a.m4a', 52001, t)));
    });
  });
}
