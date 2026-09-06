import 'package:dio/dio.dart';
import 'package:shared_preferences/shared_preferences.dart';
import '../../core/services/tenant_config.dart';

class ApiClient {
  ApiClient._();
  static final ApiClient instance = ApiClient._();

  // JWT tokens are stored in SharedPreferences (same reliable backend as
  // TenantConfig). FlutterSecureStorage's encrypted store was returning null
  // on some Android devices after rebuilds — so the Authorization header was
  // silently dropped and every request 401'd despite a valid login.
  static const _kAccess = 'access_token';
  static const _kRefresh = 'refresh_token';

  late final Dio _dio;
  bool _initialized = false;

  /// Called when the session can't be recovered (refresh failed / expired).
  /// The app wires this to log out + route to the login screen so the user
  /// gets a clean re-login instead of a raw 401 error.
  static void Function()? onSessionExpired;

  // Single-flight refresh: concurrent 401s share ONE refresh call instead of
  // each firing their own (which races and can spuriously fail).
  Future<bool>? _refreshing;

  Dio get dio {
    if (!_initialized) init();
    return _dio;
  }

  void init() {
    if (_initialized) return;
    _initialized = true;
    _dio = Dio(BaseOptions(
      // baseUrl is set per-request below from TenantConfig, allowing
      // workspace switches without recreating the client.
      connectTimeout: const Duration(seconds: 15),
      receiveTimeout: const Duration(seconds: 30),
      headers: {'Content-Type': 'application/json'},
    ));

    _dio.interceptors.add(InterceptorsWrapper(
      onRequest: (options, handler) async {
        // Resolve tenant URL dynamically
        final tenantBase = TenantConfig.instance.apiBaseUrl;
        options.baseUrl = '$tenantBase/api/v1';
        _applyTenantHeaders(options.headers);

        // JWT
        final prefs = await SharedPreferences.getInstance();
        final token = prefs.getString(_kAccess);
        if (token != null && token.isNotEmpty) {
          options.headers['Authorization'] = 'Bearer $token';
        }

        handler.next(options);
      },
      onError: (error, handler) async {
        // Don't try to refresh on the auth endpoints themselves.
        final path = error.requestOptions.path;
        final isAuthCall = path.contains('/auth/refresh/') || path.contains('/auth/login/');

        if (error.response?.statusCode == 401 && !isAuthCall) {
          final refreshed = await _tryRefresh();
          if (refreshed) {
            final prefs = await SharedPreferences.getInstance();
            final token = prefs.getString(_kAccess);
            error.requestOptions.headers['Authorization'] = 'Bearer $token';
            try {
              final retry = await _dio.fetch(error.requestOptions);
              return handler.resolve(retry);
            } catch (_) {}
          }
          // Unrecoverable — clear session and notify the app to go to login.
          await clearTokens();
          try {
            onSessionExpired?.call();
          } catch (_) {}
        }
        handler.next(error);
      },
    ));
  }

  Future<bool> _tryRefresh() {
    // Reuse an in-flight refresh if one is already running.
    return _refreshing ??= _doRefresh().whenComplete(() => _refreshing = null);
  }

  Future<bool> _doRefresh() async {
    final prefs = await SharedPreferences.getInstance();
    final refresh = prefs.getString(_kRefresh);
    if (refresh == null || refresh.isEmpty) return false;
    try {
      final tenantBase = TenantConfig.instance.apiBaseUrl;
      final headers = <String, dynamic>{'Content-Type': 'application/json'};
      _applyTenantHeaders(headers);
      final res = await Dio().post(
        '$tenantBase/api/v1/auth/refresh/',
        data: {'refresh': refresh},
        options: Options(headers: headers),
      );
      final access = res.data['access'] as String?;
      // Backend may or may not rotate the refresh token; keep the old one if absent.
      final newRefresh = (res.data['refresh'] as String?) ?? refresh;
      if (access == null) return false;
      await saveTokens(access: access, refresh: newRefresh);
      return true;
    } catch (_) {
      return false;
    }
  }

  Future<void> saveTokens({required String access, required String refresh}) async {
    final prefs = await SharedPreferences.getInstance();
    await prefs.setString(_kAccess, access);
    await prefs.setString(_kRefresh, refresh);
  }

  Future<void> clearTokens() async {
    final prefs = await SharedPreferences.getInstance();
    await prefs.remove(_kAccess);
    await prefs.remove(_kRefresh);
  }

  Future<String?> get accessToken async {
    final prefs = await SharedPreferences.getInstance();
    final t = prefs.getString(_kAccess);
    return (t != null && t.isNotEmpty) ? t : null;
  }

  /// Probe the current tenant URL. Returns null on success, error message on failure.
  Future<String?> testTenantConnection() async {
    try {
      final base = TenantConfig.instance.apiBaseUrl;
      final headers = <String, dynamic>{};
      _applyTenantHeaders(headers);
      final probe = await Dio(BaseOptions(
        connectTimeout: const Duration(seconds: 10),
        receiveTimeout: const Duration(seconds: 10),
      )).get('$base/api/v1/auth/tenant-info/',
          options: Options(
            headers: headers,
            validateStatus: (s) => s != null && s < 500,
          ));
      if (probe.statusCode == null || probe.statusCode! >= 500) {
        return 'Server error (HTTP ${probe.statusCode}). Check the workspace URL.';
      }
      return null;
    } on DioException catch (e) {
      if (e.type == DioExceptionType.connectionTimeout || e.type == DioExceptionType.receiveTimeout) {
        return 'Connection timed out. Check your internet & workspace URL.';
      }
      if (e.type == DioExceptionType.connectionError) {
        return 'Cannot reach this workspace. Verify the spelling.';
      }
      if (e.response?.statusCode == 404) {
        return 'Workspace not found. Double-check the name.';
      }
      return 'Connection failed: ${e.message ?? e.type.name}';
    } catch (e) {
      return 'Unexpected error: $e';
    }
  }

  /// A message worth showing the user.
  ///
  /// DRF reports a rejected save as {"field": ["reason"]} — not as `message`
  /// or `detail`. Reading only those two keys turned every validation failure
  /// into a blank "An error occurred", which is how a mobile form that sent an
  /// invalid choice on EVERY submit went unexplained: the server said exactly
  /// what was wrong and the app threw it away. Field errors are named here so
  /// the next mismatch is legible instead of mysterious.
  static String errorMessage(dynamic error) {
    if (error is DioException) {
      final data = error.response?.data;
      if (data is Map) {
        final direct = data['message'] as String? ?? data['detail'] as String?;
        if (direct != null && direct.isNotEmpty) return direct;

        final fieldErrors = <String>[];
        data.forEach((key, value) {
          if (key == 'message' || key == 'detail') return;
          final text = value is List
              ? value.map((v) => v.toString()).join(' ')
              : value.toString();
          if (text.isEmpty) return;
          // non_field_errors has no useful label to show.
          fieldErrors.add(key == 'non_field_errors' ? text : '$key: $text');
        });
        if (fieldErrors.isNotEmpty) {
          // Two at most — a toast is not a form, and the first error is
          // almost always the actionable one.
          return fieldErrors.take(2).join('\n');
        }
        return 'An error occurred.';
      }
      if (error.type == DioExceptionType.connectionTimeout) return 'Connection timeout. Check your internet.';
      if (error.type == DioExceptionType.connectionError) return 'Cannot connect to server. Check workspace URL.';
      if (error.response?.statusCode == 404) return 'Workspace not found or endpoint missing.';
    }
    return 'An unexpected error occurred.';
  }

  void _applyTenantHeaders(Map<String, dynamic> headers) {
    final config = TenantConfig.instance;
    final host = config.tenantHost;
    final workspace = config.workspaceId;
    if (host == null || host.isEmpty) return;

    headers['X-Tenant-Domain'] = host;
    headers['X-Workspace-ID'] = workspace ?? host;

    if (workspace != null && workspace.isNotEmpty) {
      headers['X-Tenant'] = workspace;
      headers['X-Tenant-Schema'] = workspace;
      headers['X-DTS-Schema'] = workspace;
    }

    if (TenantConfig.useLocalApi) {
      headers['Host'] = host;
    }
  }
}
