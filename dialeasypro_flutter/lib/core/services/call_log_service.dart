import 'dart:async';
import 'dart:io';

import 'package:flutter/services.dart';

// ============================================================
// DialSathi — Call outcome from the phone's own call log
//
// The app cannot measure a call itself. While it is running the phone's
// dialer owns the screen and Android freezes this app, so a ticking timer
// stops; and Android's "call started" signal fires when dialling begins, not
// when the customer answers, so every outgoing call looked connected. Every
// connect rate and talk-time figure in the CRM was built on those two numbers.
//
// The system call log records the real talk time once the call ends, and a
// duration of 0 means nobody picked up. That is what calls are saved with.
// ============================================================

/// What a finished call is saved as.
class CallOutcome {
  final int durationSec;
  /// Null when the phone could not say — the agent confirms it on the
  /// post-call screen.
  final bool? connected;
  final DateTime endedAt;
  /// Where the figures came from: 'call_log' or 'estimate'.
  final String source;

  const CallOutcome({
    required this.durationSec,
    required this.connected,
    required this.endedAt,
    required this.source,
  });
}

/// Decide a call's figures from what is known. Pure, so it can be tested.
///
/// [log] is the call-log entry ({found, durationSec, dateMillis}) or null.
/// Without one, the duration is estimated from timestamps — never from the
/// frozen timer — and "connected" is left for the agent to confirm.
CallOutcome decideCallOutcome({
  required Map<String, dynamic>? log,
  required DateTime dialedAt,
  required DateTime endedAt,
  DateTime? offHookAt,
}) {
  if (log != null && log['found'] == true) {
    final duration = (log['durationSec'] as num?)?.toInt() ?? 0;
    final placed = log['dateMillis'] is num
        ? DateTime.fromMillisecondsSinceEpoch((log['dateMillis'] as num).toInt())
        : dialedAt;
    return CallOutcome(
      durationSec: duration,
      connected: duration > 0,
      // The log's DATE is when the call was placed; ringing is not in the
      // duration, so this is when the conversation ended at the earliest.
      endedAt: duration > 0 ? placed.add(Duration(seconds: duration)) : endedAt,
      source: 'call_log',
    );
  }
  final from = offHookAt ?? dialedAt;
  final estimate = endedAt.difference(from).inSeconds;
  return CallOutcome(
    durationSec: estimate < 0 ? 0 : estimate,
    connected: null,
    endedAt: endedAt,
    source: 'estimate',
  );
}

class CallLogService {
  CallLogService._();
  static final CallLogService instance = CallLogService._();

  static const _channel = MethodChannel('dialeasypro/call_log');

  /// The call-log entry for the call to [number] dialled at [dialedAt], or
  /// null. The phone writes the entry a moment after the call ends, so this
  /// retries for a few seconds.
  Future<Map<String, dynamic>?> findOutgoing(String number, DateTime dialedAt) async {
    if (!Platform.isAndroid) return null;
    for (var attempt = 0; attempt < 5; attempt++) {
      try {
        final res = await _channel.invokeMapMethod<String, dynamic>('findOutgoing', {
          'number': number,
          'sinceMillis': dialedAt.millisecondsSinceEpoch,
        });
        if (res == null) return null;
        if (res['found'] == true) return res;
        // No permission or no call log on this device: retrying won't help.
        if (res['reason'] != 'not_yet') return null;
      } on MissingPluginException {
        return null;
      } on PlatformException {
        return null;
      }
      await Future.delayed(const Duration(milliseconds: 700));
    }
    return null;
  }
}
