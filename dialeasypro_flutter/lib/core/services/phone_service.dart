import 'dart:async';
import 'package:flutter_phone_direct_caller/flutter_phone_direct_caller.dart';
import 'package:permission_handler/permission_handler.dart';
import 'package:phone_state/phone_state.dart';
import 'package:url_launcher/url_launcher.dart';
import 'package:wakelock_plus/wakelock_plus.dart';

// ============================================================
// DialEasypro — Phone Service
// Direct auto-dial + call state monitoring
// ============================================================

enum CallStatus { idle, dialing, connecting, ringing, active, ended, failed }

class PhoneCallEvent {
  final CallStatus status;
  final String? number;
  final int? durationSec;
  final DateTime timestamp;

  PhoneCallEvent({required this.status, this.number, this.durationSec})
      : timestamp = DateTime.now();
}

class PhoneService {
  PhoneService._();
  static final PhoneService instance = PhoneService._();

  final _eventController = StreamController<PhoneCallEvent>.broadcast();
  Stream<PhoneCallEvent> get events => _eventController.stream;

  StreamSubscription<PhoneState>? _phoneStateSub;
  DateTime? _callStartedAt;
  String? _currentNumber;
  Timer? _durationTimer;
  int _durationSec = 0;

  CallStatus _currentStatus = CallStatus.idle;
  CallStatus get currentStatus => _currentStatus;
  int get currentDurationSec => _durationSec;
  String? get currentNumber => _currentNumber;

  /// Initialize (or re-initialize) the phone state listener.
  ///
  /// Called on app start AND again after call permissions are granted —
  /// the stream yields nothing when attached before READ_PHONE_STATE was
  /// granted, which silently broke call detection (duration stayed 0 and
  /// recordings were never captured).
  Future<void> init() async {
    try {
      await _phoneStateSub?.cancel();
      _phoneStateSub = PhoneState.stream.listen(_onPhoneStateChange);
    } catch (e) {
      // Phone state monitoring not supported (iOS or no permission)
      // ignore: avoid_print
      print('[PhoneService] Phone state listener unavailable: $e');
    }
  }

  void _onPhoneStateChange(PhoneState state) {
    switch (state.status) {
      case PhoneStateStatus.NOTHING:
        if (_currentStatus != CallStatus.idle && _currentStatus != CallStatus.ended) {
          _endCall();
        }
        break;
      case PhoneStateStatus.CALL_STARTED:
        _currentStatus = CallStatus.active;
        _callStartedAt = DateTime.now();
        _startDurationTimer();
        WakelockPlus.enable();
        _eventController.add(PhoneCallEvent(status: CallStatus.active, number: state.number));
        break;
      case PhoneStateStatus.CALL_INCOMING:
        _currentStatus = CallStatus.ringing;
        _eventController.add(PhoneCallEvent(status: CallStatus.ringing, number: state.number));
        break;
      case PhoneStateStatus.CALL_OUTGOING:
        _currentStatus = CallStatus.dialing;
        _eventController.add(PhoneCallEvent(status: CallStatus.dialing, number: state.number));
        break;
      case PhoneStateStatus.CALL_ENDED:
        _endCall();
        break;
    }
  }

  void _startDurationTimer() {
    _durationSec = 0;
    _durationTimer?.cancel();
    _durationTimer = Timer.periodic(const Duration(seconds: 1), (_) {
      _durationSec++;
      _eventController.add(PhoneCallEvent(
        status: _currentStatus, number: _currentNumber, durationSec: _durationSec,
      ));
    });
  }

  void _endCall() {
    final endedStatus = CallStatus.ended;
    _currentStatus = endedStatus;
    _durationTimer?.cancel();
    WakelockPlus.disable();
    _eventController.add(PhoneCallEvent(
      status: endedStatus,
      number: _currentNumber,
      durationSec: _durationSec,
    ));
    // Reset after a short delay so UI can read final values
    Future.delayed(const Duration(seconds: 1), () {
      _currentStatus = CallStatus.idle;
      _callStartedAt = null;
      _currentNumber = null;
      _durationSec = 0;
    });
  }

  /// Check if we have CALL_PHONE permission
  Future<bool> hasCallPermission() async {
    final s = await Permission.phone.status;
    return s.isGranted;
  }

  /// Request CALL_PHONE permission
  Future<bool> requestCallPermission() async {
    final s = await Permission.phone.request();
    if (s.isGranted) await init(); // re-attach listener now that we can read state
    return s.isGranted;
  }

  /// Request all call-related permissions
  Future<bool> requestAllCallPermissions() async {
    final results = await [
      Permission.phone,
      Permission.contacts,
      Permission.microphone, // in-call mic recording fallback
    ].request();
    final granted = results[Permission.phone]?.isGranted == true;
    if (granted) await init(); // re-attach listener now that we can read state
    return granted;
  }

  /// Direct dial — bypasses the system dialer confirmation screen
  /// Returns true if the call was initiated successfully
  Future<bool> directDial(String phoneNumber) async {
    if (!await hasCallPermission()) {
      if (!await requestCallPermission()) {
        return false;
      }
    }

    _currentNumber = _normalizeNumber(phoneNumber);
    _currentStatus = CallStatus.dialing;
    _eventController.add(PhoneCallEvent(status: CallStatus.dialing, number: _currentNumber));

    try {
      final result = await FlutterPhoneDirectCaller.callNumber(_currentNumber!);
      return result == true;
    } catch (e) {
      _currentStatus = CallStatus.failed;
      _eventController.add(PhoneCallEvent(status: CallStatus.failed, number: _currentNumber));
      return false;
    }
  }

  /// Fallback: launch system dialer (user has to tap call button)
  Future<bool> launchDialer(String phoneNumber) async {
    final normalized = _normalizeNumber(phoneNumber);
    final uri = Uri.parse('tel:$normalized');
    if (await canLaunchUrl(uri)) {
      return await launchUrl(uri);
    }
    return false;
  }

  String _normalizeNumber(String phone) {
    final digits = phone.replaceAll(RegExp(r'[^\d+]'), '');
    if (digits.startsWith('+')) return digits;
    if (digits.startsWith('91') && digits.length == 12) return '+$digits';
    if (digits.length == 10) return '+91$digits';
    return digits;
  }

  void dispose() {
    _phoneStateSub?.cancel();
    _durationTimer?.cancel();
    _eventController.close();
  }
}
