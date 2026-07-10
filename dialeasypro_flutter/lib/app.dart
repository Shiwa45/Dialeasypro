import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:go_router/go_router.dart';
import 'core/theme/app_theme.dart';
import 'core/theme/colors.dart';
import 'data/models/addon_models.dart';
import 'features/auth/auth_provider.dart';
import 'features/auth/login_screen.dart';
import 'features/calls/calls_screen.dart';
import 'features/communications/whatsapp_send_screen.dart';
import 'features/dashboard/dashboard_screen.dart';
import 'features/dialer/dialer_screen.dart';
import 'features/dialer/queue_starter_screen.dart';
import 'features/features_provider.dart';
import 'features/hrms/my_work_screen.dart';
import 'features/leads/lead_detail_screen.dart';
import 'features/leads/lead_form_screen.dart';
import 'features/leads/lead_import_screen.dart';
import 'features/leads/leads_list_screen.dart';
import 'features/profile/profile_screen.dart';
import 'features/reports/reports_screen.dart';

final _rootKey = GlobalKey<NavigatorState>();
final _shellKey = GlobalKey<NavigatorState>();

final _routerProvider = Provider<GoRouter>((ref) {
  final authState = ref.watch(authProvider);

  return GoRouter(
    navigatorKey: _rootKey,
    initialLocation: '/',
    refreshListenable: ValueNotifier(authState.status),
    redirect: (ctx, state) {
      if (authState.isLoading) return null;
      final isAuth = authState.isAuthenticated;
      final isLoginPath = state.matchedLocation == '/login';
      if (!isAuth && !isLoginPath) return '/login';
      if (isAuth && isLoginPath) return '/';
      return null;
    },
    routes: [
      // Login (outside shell)
      GoRoute(path: '/login', builder: (_, __) => const LoginScreen()),

      // Bottom-nav shell
      ShellRoute(
        navigatorKey: _shellKey,
        builder: (ctx, state, child) => _MainShell(child: child),
        routes: [
          GoRoute(path: '/', redirect: (_, __) => '/dashboard'),
          GoRoute(path: '/dashboard', builder: (_, __) => const DashboardScreen()),
          GoRoute(
            path: '/leads',
            builder: (_, state) {
              final select = state.uri.queryParameters['select'] == 'true';
              return LeadsListScreen(selectMode: select);
            },
          ),
          GoRoute(path: '/calls', builder: (_, __) => const CallsScreen()),
          GoRoute(path: '/reports', builder: (_, __) => const ReportsScreen()),
          // Stays routable even without the HRMS module — the tab is hidden,
          // and the endpoints answer 402 if it's reached some other way.
          GoRoute(path: '/my-work', builder: (_, __) => const MyWorkScreen()),
        ],
      ),

      // Full-screen routes
      GoRoute(path: '/leads/new', builder: (_, __) => const LeadFormScreen()),
      GoRoute(path: '/leads/import', builder: (_, __) => const LeadImportScreen()),
      GoRoute(
        path: '/leads/:id',
        builder: (_, s) => LeadDetailScreen(leadId: int.parse(s.pathParameters['id']!)),
      ),
      GoRoute(
        path: '/leads/:id/edit',
        builder: (_, s) => LeadFormScreen(leadId: int.parse(s.pathParameters['id']!)),
      ),
      GoRoute(
        path: '/leads/:id/whatsapp',
        builder: (_, s) => WhatsAppSendScreen(leadId: int.parse(s.pathParameters['id']!)),
      ),
      GoRoute(path: '/profile', builder: (_, __) => const ProfileScreen()),
      GoRoute(path: '/dialer/queue', builder: (_, __) => const QueueStarterScreen()),
      GoRoute(path: '/dialer', builder: (_, __) => const DialerScreen()),
    ],
    errorBuilder: (_, state) => Scaffold(
      body: Center(
        child: Column(
          mainAxisSize: MainAxisSize.min,
          children: [
            const Text('404', style: TextStyle(fontFamily: 'SpaceGrotesk', fontWeight: FontWeight.w700, fontSize: 72, color: AppColors.yellow)),
            const Text('Page not found', style: TextStyle(fontFamily: 'SpaceGrotesk', fontWeight: FontWeight.w600, fontSize: 18)),
            const SizedBox(height: 20),
            ElevatedButton(onPressed: () => GoRouter.of(_).go('/'), child: const Text('Go Home')),
          ],
        ),
      ),
    ),
  );
});

// ─── BOTTOM NAV SHELL ───────────────────────────────────────
class _MainShell extends ConsumerStatefulWidget {
  final Widget child;
  const _MainShell({required this.child});

  @override
  ConsumerState<_MainShell> createState() => _MainShellState();
}

class _MainShellState extends ConsumerState<_MainShell> {
  int _idx = 0;

  static const _coreTabs = [
    _Tab(path: '/dashboard', icon: Icons.dashboard_outlined, activeIcon: Icons.dashboard, label: 'Home'),
    _Tab(path: '/leads',     icon: Icons.people_outline,     activeIcon: Icons.people,    label: 'Leads'),
    _Tab(path: '/calls',     icon: Icons.phone_outlined,     activeIcon: Icons.phone,     label: 'Calls'),
    _Tab(path: '/reports',   icon: Icons.bar_chart_outlined, activeIcon: Icons.bar_chart, label: 'Reports'),
  ];

  static const _myWorkTab = _Tab(
    path: '/my-work', icon: Icons.badge_outlined, activeIcon: Icons.badge, label: 'My Work',
  );

  /// Add-on tabs are appended, never inserted, so `_idx` stays pointing at the
  /// same tab when the features request resolves after first paint.
  List<_Tab> get _tabs => [
        ..._coreTabs,
        if (ref.features.hasModule(Mod.hrms)) _myWorkTab,
      ];

  @override
  Widget build(BuildContext context) {
    final tabs = _tabs;
    // If the module is revoked mid-session the list shrinks under us.
    if (_idx >= tabs.length) _idx = 0;

    return Scaffold(
      body: widget.child,
      bottomNavigationBar: Container(
        decoration: const BoxDecoration(
          border: Border(top: BorderSide(color: AppColors.black, width: 2)),
        ),
        child: BottomNavigationBar(
          currentIndex: _idx,
          onTap: (i) {
            setState(() => _idx = i);
            context.go(tabs[i].path);
          },
          backgroundColor: AppColors.white,
          selectedItemColor: AppColors.black,
          unselectedItemColor: AppColors.grey,
          type: BottomNavigationBarType.fixed,
          elevation: 0,
          items: tabs.asMap().entries.map((e) => BottomNavigationBarItem(
            icon: Padding(
              padding: const EdgeInsets.only(bottom: 3),
              child: Container(
                padding: EdgeInsets.all(_idx == e.key ? 4 : 0),
                decoration: _idx == e.key ? BoxDecoration(color: AppColors.yellow, border: Border.all(color: AppColors.black, width: 1.5)) : null,
                child: Icon(_idx == e.key ? e.value.activeIcon : e.value.icon, size: 20),
              ),
            ),
            label: e.value.label,
          )).toList(),
          selectedLabelStyle: const TextStyle(fontFamily: 'SpaceGrotesk', fontWeight: FontWeight.w700, fontSize: 10),
          unselectedLabelStyle: const TextStyle(fontFamily: 'DMSans', fontSize: 10),
        ),
      ),
    );
  }
}

class _Tab {
  final String path, label;
  final IconData icon, activeIcon;
  const _Tab({required this.path, required this.icon, required this.activeIcon, required this.label});
}

// ─── ROOT APP ───────────────────────────────────────────────
class DialEasyproApp extends ConsumerWidget {
  const DialEasyproApp({super.key});

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final router = ref.watch(_routerProvider);
    return MaterialApp.router(
      title: 'DialEasypro',
      theme: AppTheme.theme,
      routerConfig: router,
      debugShowCheckedModeBanner: false,
      builder: (ctx, child) => MediaQuery(
        data: MediaQuery.of(ctx).copyWith(textScaler: TextScaler.noScaling),
        child: child!,
      ),
    );
  }
}
