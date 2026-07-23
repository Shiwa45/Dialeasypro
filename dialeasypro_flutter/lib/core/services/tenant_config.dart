import 'package:shared_preferences/shared_preferences.dart';

// ============================================================
// DialEasypro — Tenant Configuration
//
// Multi-tenant Django backend uses django-tenants with schema-based
// isolation. Each tenant has its own subdomain (e.g.,
// acmecorp.dialeasypro.com → acmecorp schema).
//
// The Flutter app needs to know which tenant to talk to. We store:
//   - tenantSlug: the workspace identifier (e.g., "acmecorp" or
//     "acmecorp.example.com")
//   - customBaseUrl: optional full override (for self-hosted/dev)
//
// On each API request, the resolved URL points to the correct
// tenant's subdomain, so django-tenants middleware routes to the
// right schema automatically based on the Host header.
// ============================================================

class TenantConfig {
  TenantConfig._();
  static final TenantConfig instance = TenantConfig._();

  /// Default root domain for the SaaS deployment (overridable via --dart-define)
  static const String defaultRootDomain = String.fromEnvironment(
    'ROOT_DOMAIN',
    defaultValue: 'easyian.shop',
  );

  /// Default API base URL when no tenant is configured (e.g. dev)
  static const String defaultBaseUrl = String.fromEnvironment(
    'API_BASE_URL',
    defaultValue: 'https://easyian.shop',
  );

  /// Local development mode. Android emulators reach the host machine via
  /// 10.0.2.2, not localhost.
  static const bool useLocalApi = bool.fromEnvironment(
    'USE_LOCAL_API',
    defaultValue: false,
  );

  static const _kTenantSlug = 'tenant_slug';
  static const _kCustomUrl = 'tenant_custom_url';

  String? _tenantSlug;
  String? _customBaseUrl;
  bool _loaded = false;

  String? get tenantSlug => _tenantSlug;
  String? get customBaseUrl => _customBaseUrl;
  bool get hasTenant => (_tenantSlug != null && _tenantSlug!.isNotEmpty) ||
                       (_customBaseUrl != null && _customBaseUrl!.isNotEmpty);

  String? get tenantHost {
    final slug = _tenantSlug?.trim();
    if (slug == null || slug.isEmpty) return null;
    return _normalizeTenantInput(slug);
  }

  String? get workspaceId {
    final host = tenantHost;
    if (host == null || host.isEmpty) return null;
    return host.split('.').first;
  }

  /// Load from persistent storage. Call once on app start.
  Future<void> load() async {
    if (_loaded) return;
    _loaded = true;
    try {
      final prefs = await SharedPreferences.getInstance();
      _tenantSlug = prefs.getString(_kTenantSlug);
      _customBaseUrl = prefs.getString(_kCustomUrl);
    } catch (_) {}
  }

  /// Save tenant slug (e.g. "acmecorp") and optional full URL override
  Future<void> save({String? slug, String? customUrl}) async {
    final normalizedSlug = slug == null || slug.trim().isEmpty
        ? null
        : _normalizeTenantInput(slug.trim());
    _tenantSlug = normalizedSlug;
    _customBaseUrl = customUrl?.trim().isEmpty == true ? null : customUrl?.trim();
    final prefs = await SharedPreferences.getInstance();
    if (_tenantSlug != null) {
      await prefs.setString(_kTenantSlug, _tenantSlug!);
    } else {
      await prefs.remove(_kTenantSlug);
    }
    if (_customBaseUrl != null) {
      await prefs.setString(_kCustomUrl, _customBaseUrl!);
    } else {
      await prefs.remove(_kCustomUrl);
    }
  }

  /// Clear all tenant config (used on "switch workspace")
  Future<void> clear() async {
    _tenantSlug = null;
    _customBaseUrl = null;
    final prefs = await SharedPreferences.getInstance();
    await prefs.remove(_kTenantSlug);
    await prefs.remove(_kCustomUrl);
    // Tokens are tenant-specific, clear them too. They live in SharedPreferences
    // (see ApiClient) — clear them there.
    await prefs.remove('access_token');
    await prefs.remove('refresh_token');
  }

  /// Resolve the actual API base URL based on current config.
  /// Logic:
  ///   1. If customBaseUrl is set → use it directly (self-hosted/dev)
  ///   2. If tenantSlug starts with http(s):// → use as-is
  ///   3. If tenantSlug contains a dot → treat as full domain
  ///   4. Otherwise → treat as subdomain: https://{slug}.{rootDomain}
  ///   5. Fallback → defaultBaseUrl
  String get apiBaseUrl {
    if (useLocalApi) {
      return _normalizeUrl(defaultBaseUrl);
    }

    // Custom URL override always wins
    if (_customBaseUrl != null && _customBaseUrl!.isNotEmpty) {
      return _normalizeUrl(_customBaseUrl!);
    }

    final slug = _tenantSlug;
    if (slug == null || slug.isEmpty) {
      return defaultBaseUrl;
    }

    if (slug.startsWith('http://') || slug.startsWith('https://')) {
      return _normalizeUrl(slug);
    }
    if (slug.contains('.')) {
      // e.g. "acmecorp.dialeasypro.com" or "crm.acmecorp.com"
      return 'https://$slug';
    }
    // Subdomain mode
    return 'https://$slug.$defaultRootDomain';
  }

  /// Get the URL that an agent would visit in their browser for this tenant
  String get displayUrl {
    final base = apiBaseUrl;
    return base.replaceAll(RegExp(r'/$'), '');
  }

  String _normalizeUrl(String url) {
    // Strip trailing slashes
    return url.replaceAll(RegExp(r'/+$'), '');
  }

  String _normalizeTenantInput(String value) {
    var tenant = value.trim();
    tenant = tenant.replaceAll(RegExp(r'^https?://'), '');
    tenant = tenant.split('/').first;
    tenant = tenant.split(':').first;
    return tenant.toLowerCase();
  }

  /// For display only — shows "acmecorp" or "crm.acmecorp.com" or "Custom URL"
  String get summary {
    if (_customBaseUrl != null && _customBaseUrl!.isNotEmpty) {
      return _customBaseUrl!.replaceAll(RegExp(r'^https?://'), '');
    }
    if (_tenantSlug != null && _tenantSlug!.isNotEmpty) {
      return _tenantSlug!;
    }
    return 'Not configured';
  }
}
