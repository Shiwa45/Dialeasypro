import 'dart:async';
import 'dart:convert';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:shared_preferences/shared_preferences.dart';
import '../../core/services/notification_service.dart';
import '../../core/services/presence_service.dart';
import '../../data/services/api_client.dart';
import '../../data/services/services.dart';
import '../../data/models/models.dart';

enum AuthStatus { loading, authenticated, unauthenticated }

class AuthState {
  final AuthStatus status;
  final Agent? agent;
  final String? error;

  const AuthState({this.status = AuthStatus.loading, this.agent, this.error});

  bool get isAuthenticated => status == AuthStatus.authenticated;
  bool get isLoading => status == AuthStatus.loading;
  bool get isUnauthenticated => status == AuthStatus.unauthenticated;
}

class AuthNotifier extends StateNotifier<AuthState> {
  AuthNotifier() : super(const AuthState()) {
    // When the API client can't recover a session (refresh failed/expired),
    // flip to unauthenticated so the router sends the user to login cleanly
    // instead of surfacing a raw 401 on whatever screen they were on.
    ApiClient.onSessionExpired = () {
      if (mounted) state = const AuthState(status: AuthStatus.unauthenticated);
    };
    _init();
  }

  static const _kAgentKey = 'cached_agent';

  Future<void> _init() async {
    final token = await ApiClient.instance.accessToken;
    if (token == null) {
      state = const AuthState(status: AuthStatus.unauthenticated);
      return;
    }
    // Load cached agent for instant render
    final prefs = await SharedPreferences.getInstance();
    final raw = prefs.getString(_kAgentKey);
    if (raw != null) {
      try {
        final agent = Agent.fromJson(json.decode(raw));
        state = AuthState(status: AuthStatus.authenticated, agent: agent);
      } catch (_) {}
    }
    // Refresh from server
    try {
      final fresh = await AuthService.instance.getProfile();
      await _cache(fresh);
      state = AuthState(status: AuthStatus.authenticated, agent: fresh);
    } catch (_) {
      if (state.agent == null) state = const AuthState(status: AuthStatus.unauthenticated);
    }
  }

  Future<bool> login(String email, String password) async {
    // No global "loading" here. The login screen shows its own spinner, and
    // flipping the app-wide state to loading rebuilt the router, which let the
    // dashboard mount before a token existed: its requests 401'd, the app
    // bounced to the login screen, then jumped in a second later when this
    // call finished — the "logs out, then logs itself in" flicker.
    try {
      final res = await AuthService.instance.login(email, password);
      await ApiClient.instance.saveTokens(access: res.access, refresh: res.refresh);
      await _cache(res.agent);
      state = AuthState(status: AuthStatus.authenticated, agent: res.agent);
      // Arm this phone's follow-up reminders. Android then raises them at the
      // right time whether or not the app is running or the network is up,
      // which is the only delivery path that does not depend on push.
      // Deliberately not awaited: a slow or failed sync must not hold up the
      // login it follows.
      unawaited(NotificationService.instance.requestPermissions());
      unawaited(NotificationService.instance.syncFollowupReminders());
      // Whatever is already unread is history this agent is about to see in
      // the app. Record it as told so the shade carries what arrives NEXT,
      // rather than a stack of the backlog a minute after signing in.
      unawaited(NotificationService.instance.syncServerNotifications(silent: true));
      return true;
    } catch (e) {
      state = AuthState(status: AuthStatus.unauthenticated, error: ApiClient.errorMessage(e));
      return false;
    }
  }

  Future<void> logout() async {
    // Drop the reminders and the device registration before the token goes.
    // Without this the next person to sign in on this handset keeps receiving
    // the previous agent's follow-ups.
    // Offline on the Live Agents board while the token still works — the
    // status call needs it. (The work session's own state resets with the app.)
    PresenceService.instance.endSession();
    try {
      await NotificationService.instance.cancelAll();
      await NotificationService.instance.clearAnnounced();
      await NotificationsService.instance.registerDevice('');
    } catch (_) {}
    await ApiClient.instance.clearTokens();
    final prefs = await SharedPreferences.getInstance();
    await prefs.remove(_kAgentKey);
    // A break in progress belongs to this agent, not the next one to sign in.
    await prefs.remove('work_on_break');
    await prefs.remove('work_break_reason');
    state = const AuthState(status: AuthStatus.unauthenticated);
  }

  Future<void> refreshProfile() async {
    try {
      final fresh = await AuthService.instance.getProfile();
      await _cache(fresh);
      state = AuthState(status: AuthStatus.authenticated, agent: fresh);
    } catch (_) {}
  }

  Future<void> _cache(Agent agent) async {
    final prefs = await SharedPreferences.getInstance();
    await prefs.setString(_kAgentKey, json.encode({
      'id': agent.id, 'email': agent.email, 'name': agent.name, 'phone': agent.phone,
      'employee_id': agent.employeeId, 'role': agent.role, 'role_display': agent.roleDisplay,
      'is_tenant_admin': agent.isTenantAdmin, 'is_active': agent.isActive,
      'profile_photo_url': agent.profilePhotoUrl, 'last_active_at': agent.lastActiveAt,
      'created_at': agent.createdAt, 'timezone': agent.timezone,
      'total_login_count': agent.totalLoginCount,
    }));
  }
}

final authProvider = StateNotifierProvider<AuthNotifier, AuthState>((_) => AuthNotifier());
final currentAgentProvider = Provider<Agent?>((ref) => ref.watch(authProvider).agent);

// ─── Persisted user preferences ─────────────────────────────
class UserPrefs {
  static const _kWhatsAppMode = 'pref_whatsapp_mode';

  static Future<String> getWhatsAppMode() async {
    final prefs = await SharedPreferences.getInstance();
    return prefs.getString(_kWhatsAppMode) ?? 'native';
  }

  static Future<void> setWhatsAppMode(String mode) async {
    final prefs = await SharedPreferences.getInstance();
    await prefs.setString(_kWhatsAppMode, mode);
  }
}

final whatsappModeProvider = StateProvider<String>((_) => 'native');
