// APP-M1: which audio file belongs to a call. A time-only match used to be
// accepted up to 70 seconds from the call's end, in folders that also hold
// voice memos — so another call's recording, or personal audio, could be
// attached to a customer call.

import 'package:flutter_test/flutter_test.dart';

import 'package:dialeasypro/core/services/call_recording_service.dart';
import 'package:dialeasypro/core/services/setup_service.dart';

void main() {
  final end = DateTime(2026, 9, 29, 14, 32, 5);
  const phone = '+919812300001';

  ({int score, String matchedBy})? score(String name, {int secondsAfterEnd = 3}) =>
      scoreRecordingCandidate(
        fileName: name,
        modified: end.add(Duration(seconds: secondsAfterEnd)),
        phoneNumber: phone,
        callEnd: end,
      );

  test('the call number in the name is a strong match', () {
    expect(score('Call recording 9812300001_20260929143205.m4a')?.matchedBy, 'filename_number');
    expect(score('+91 98123 00001 2026-09-29.m4a')?.matchedBy, 'filename_number');
    expect(score('919812300001.amr', secondsAfterEnd: 60)?.matchedBy, 'filename_number');
  });

  test("a file named with someone else's number is never used", () {
    expect(score('Call recording 9876500002_20260929143205.m4a'), isNull);
  });

  test('a nameless file counts only right at the end of the call', () {
    expect(score('Call_20260929143205.m4a', secondsAfterEnd: 8)?.matchedBy, 'timestamp');
    expect(score('Call_20260929143205.m4a', secondsAfterEnd: 45), isNull,
        reason: '45 seconds out could be the next call');
  });

  test('a strong match outranks a time-only one', () {
    final strong = score('9812300001.m4a', secondsAfterEnd: 30)!;
    final weak = score('recording.m4a', secondsAfterEnd: 1)!;
    expect(strong.score, greaterThan(weak.score));
  });

  // ---- Found on the live system (Oct 2026) ------------------------------

  final start = end.subtract(const Duration(seconds: 35));

  test('a recorder that stamps yyMMddHHmm is not mistaken for another number', () {
    // "Jagdeep-2610141413.mp3": the contact's name and a 10-digit stamp.
    final near = DateTime(2026, 10, 14, 14, 13, 30);
    expect(looksLikeTimestamp('2610141413', near), isTrue);
    expect(looksLikeTimestamp('9812300001', near), isFalse);
    final s = scoreRecordingCandidate(
      fileName: 'Jagdeep-2610141413.mp3',
      modified: near.add(const Duration(seconds: 3)),
      phoneNumber: phone,
      callEnd: near,
      leadName: 'Jagdeep',
    );
    expect(s?.matchedBy, 'filename_name');
  });

  test('the number in the name is still a strong match next to a stamp', () {
    final near = DateTime(2026, 10, 14, 14, 13, 30);
    final s = scoreRecordingCandidate(
      fileName: '+919812300001-2610141413.mp3',
      modified: near,
      phoneNumber: phone,
      callEnd: near,
    );
    expect(s?.matchedBy, 'filename_number');
  });

  test('a file longer than the whole call is not its recording', () {
    expect(
      scoreRecordingCandidate(
        fileName: '9812300001.m4a', modified: end, phoneNumber: phone,
        callEnd: end, callStart: start, fileDurationSec: 300,
      ),
      isNull,
    );
    expect(
      scoreRecordingCandidate(
        fileName: '9812300001.m4a', modified: end, phoneNumber: phone,
        callEnd: end, callStart: start, fileDurationSec: 18,
      )?.matchedBy,
      'filename_number',
    );
  });

  test('the length closest to the talk time wins', () {
    final close = scoreRecordingCandidate(
      fileName: '9812300001_a.m4a', modified: end, phoneNumber: phone,
      callEnd: end, callStart: start, fileDurationSec: 19, talkSec: 18,
    )!;
    final far = scoreRecordingCandidate(
      fileName: '9812300001_b.m4a', modified: end, phoneNumber: phone,
      callEnd: end, callStart: start, fileDurationSec: 2, talkSec: 18,
    )!;
    expect(close.score, greaterThan(far.score));
  });

  test("the lead's name in a file name counts only for a name of 4+ letters", () {
    expect(score('Ravi Kumar_241017_143205.m4a', secondsAfterEnd: 60), isNull);
    final s = scoreRecordingCandidate(
      fileName: 'Ravi Kumar_241017_143205.m4a',
      modified: end.add(const Duration(seconds: 60)),
      phoneNumber: phone, callEnd: end, leadName: 'Ravi Kumar',
    );
    expect(s?.matchedBy, 'filename_name');
    expect(
      scoreRecordingCandidate(
        fileName: 'Al_143205.m4a', modified: end.add(const Duration(seconds: 60)),
        phoneNumber: phone, callEnd: end, leadName: 'Al',
      ),
      isNull,
    );
  });

  test('phones with their own call recorder leave the microphone alone', () {
    expect(brandHasCallRecorder(PhoneBrand.xiaomi), isTrue);
    expect(brandHasCallRecorder(PhoneBrand.samsung), isTrue);
    expect(brandHasCallRecorder(PhoneBrand.google), isFalse);
    expect(brandHasCallRecorder(PhoneBrand.motorola), isFalse);
  });
}
