// ─────────────────────────────────────────────────────────────
// Tenant plan features + add-on modules.
//
// Drives UI gating only. Hiding a tab is a convenience — every gated endpoint
// is re-checked server-side and answers 402 `upgrade_required` regardless of
// what this client believes.
//
// Fails open to "nothing enabled" on error: a caller with a flaky connection
// should see the core dialler, not a crash.
// ─────────────────────────────────────────────────────────────
import 'package:flutter_riverpod/flutter_riverpod.dart';

import '../data/models/addon_models.dart';
import '../data/services/addon_services.dart';
import 'auth/auth_provider.dart';

final tenantFeaturesProvider = FutureProvider<TenantFeatures>((ref) async {
  // Re-fetch after a login/logout: a different agent may be on a different
  // tenant, and the cached answer would be for the wrong workspace.
  final auth = ref.watch(authProvider);
  if (!auth.isAuthenticated) return const TenantFeatures.empty();

  try {
    return await FeaturesService.instance.fetch();
  } catch (_) {
    return const TenantFeatures.empty();
  }
});

/// Synchronous view of the features, safe to call during build.
/// Returns "nothing enabled" while the request is still in flight.
extension TenantFeaturesRef on WidgetRef {
  TenantFeatures get features =>
      watch(tenantFeaturesProvider).valueOrNull ?? const TenantFeatures.empty();
}
