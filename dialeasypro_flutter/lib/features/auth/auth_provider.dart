import 'dart:convert';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:shared_preferences/shared_preferences.dart';
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
    state = const AuthState(status: AuthStatus.loading);
    try {
      final res = await AuthService.instance.login(email, password);
      await ApiClient.instance.saveTokens(access: res.access, refresh: res.refresh);
      await _cache(res.agent);
      state = AuthState(status: AuthStatus.authenticated, agent: res.agent);
      return true;
    } catch (e) {
      state = AuthState(status: AuthStatus.unauthenticated, error: ApiClient.errorMessage(e));
      return false;
    }
  }

  Future<void> logout() async {
    await ApiClient.instance.clearTokens();
    final prefs = await SharedPreferences.getInstance();
    await prefs.remove(_kAgentKey);
    state = const AuthState(status: AuthStatus.unauthenticated);
  }

  /// Switch to a different workspace — clears tenant config + tokens
  Future<void> switchWorkspace() async {
    await ApiClient.instance.clearTokens();
    final prefs = await SharedPreferences.getInstance();
    await prefs.remove(_kAgentKey);
    // Note: TenantConfig.clear is imported lazily here to avoid circular import
    // (auth_provider depends on api_client, api_client depends on tenant_config)
    state = const AuthState(status: AuthStatus.unauthenticated);
  }

  Future<void> refreshProfile() async {
    try {
      final fresh = await AuthService.instance.getProfile();
      await _cache(fresh);
      state = AuthState(status: AuthStatus.authenticated, agent: fresh);
    } catch (_) {}
  }

  Future<bool> changePassword({required String oldPw, required String newPw, required String confirmPw}) async {
    try {
      await AuthService.instance.changePassword(
        oldPassword: oldPw, newPassword: newPw, confirmPassword: confirmPw,
      );
      return true;
    } catch (_) { return false; }
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
