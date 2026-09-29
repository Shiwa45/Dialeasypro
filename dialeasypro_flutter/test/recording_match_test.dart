// APP-M1: which audio file belongs to a call. A time-only match used to be
// accepted up to 70 seconds from the call's end, in folders that also hold
// voice memos — so another call's recording, or personal audio, could be
// attached to a customer call.

import 'package:flutter_test/flutter_test.dart';

import 'package:dialeasypro/core/services/call_recording_service.dart';

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
}
