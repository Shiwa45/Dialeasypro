import 'dart:async';

import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:go_router/go_router.dart';
import 'core/services/notification_service.dart';
import 'core/services/call_recording_service.dart';
import 'core/services/setup_service.dart';
import 'core/theme/app_theme.dart';
import 'core/theme/colors.dart';
import 'data/models/addon_models.dart';
import 'features/notifications/notifications_screen.dart';
import 'features/auth/auth_provider.dart';
import 'features/auth/login_screen.dart';
import 'features/calls/calls_screen.dart';
import 'features/communications/whatsapp_send_screen.dart';
import 'features/dashboard/dashboard_screen.dart';
import 'features/dialer/dialer_screen.dart';
import 'features/dialer/queue_starter_screen.dart';
import 'features/features_provider.dart';
import 'features/hrms/my_work_screen.dart';
import 'features/leads/followups_screen.dart';
import 'features/leads/lead_detail_screen.dart';
import 'features/leads/lead_form_screen.dart';
import 'features/leads/lead_import_screen.dart';
import 'features/leads/leads_list_screen.dart';
import 'features/profile/profile_screen.dart';
import 'features/reports/reports_screen.dart';
import 'features/setup/setup_wizard_screen.dart';

final _rootKey = GlobalKey<NavigatorState>();
final _shellKey = GlobalKey<NavigatorState>();

/// Routes a tapped notification once the router exists.
///
/// The tap can arrive before the first frame — Android launches the app to
/// deliver it — so this holds the route until there is a navigator to send it
/// to, rather than dropping it.
StreamSubscription<String>? _notificationTapSub;
String? _pendingNotificationRoute;

void _bindNotificationTaps(GoRouter router) {
  _notificationTapSub?.cancel();
  _notificationTapSub = NotificationService.instance.onOpenRoute.listen((route) {
    if (route.isEmpty) return;
    final nav = _rootKey.currentState;
    if (nav == null) {
      _pendingNotificationRoute = route;
      return;
    }
    router.push(route);
  });

  // Anything that arrived before the router was ready.
  final pending = _pendingNotificationRoute;
  if (pending != null) {
    _pendingNotificationRoute = null;
    WidgetsBinding.instance.addPostFrameCallback((_) => router.push(pending));
  }
}

final _routerProvider = Provider<GoRouter>((ref) {
  final authState = ref.watch(authProvider);

  final router = GoRouter(
    navigatorKey: _rootKey,
    initialLocation: '/',
    refreshListenable: ValueNotifier(authState.status),
    redirect: (ctx, state) {
      if (authState.isLoading) return null;
      final isAuth = authState.isAuthenticated;
      final isLoginPath = state.matchedLocation == '/login';
      if (!isAuth && !isLoginPath) return '/login';
      if (isAuth && isLoginPath) return '/';
      // First run: send the agent through permissions and call-recording setup
      // before they start dialling, rather than letting them discover later
      // that nothing was recorded.
      final isSetupPath = state.matchedLocation == '/setup';
      if (isAuth && !SetupService.instance.isCompleteSync && !isSetupPath) {
        return '/setup';
      }
      return null;
    },
    routes: [
      // Login (outside shell)
      GoRoute(path: '/login', builder: (_, __) => const LoginScreen()),

      // First-run setup (outside the shell — no bottom nav during setup)
      GoRoute(path: '/setup', builder: (_, __) => const SetupWizardScreen()),

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
      GoRoute(path: '/followups', builder: (_, __) => const FollowupsScreen()),
      GoRoute(path: '/notifications', builder: (_, __) => const NotificationsScreen()),
      GoRoute(path: '/dialer/queue', builder: (_, __) => const QueueStarterScreen()),
      GoRoute(path: '/dialer', builder: (_, __) => const DialerScreen()),
    ],
    errorBuilder: (_, state) => Scaffold(
      body: Center(
        child: Column(
          mainAxisSize: MainAxisSize.min,
          children: [
            const Text('404', style: TextStyle(fontFamily: 'Archivo', fontWeight: FontWeight.w700, fontSize: 72, color: AppColors.yellow)),
            const Text('Page not found', style: TextStyle(fontFamily: 'Archivo', fontWeight: FontWeight.w600, fontSize: 18)),
            const SizedBox(height: 20),
            ElevatedButton(onPressed: () => GoRouter.of(_).go('/'), child: const Text('Go Home')),
          ],
        ),
      ),
    ),
  );

  _bindNotificationTaps(router);
  ref.onDispose(() => _notificationTapSub?.cancel());
  return router;
});

// ─── BOTTOM NAV SHELL ───────────────────────────────────────
class _MainShell extends ConsumerStatefulWidget {
  final Widget child;
  const _MainShell({required this.child});

  @override
  ConsumerState<_MainShell> createState() => _MainShellState();
}

class _MainShellState extends ConsumerState<_MainShell>
    with WidgetsBindingObserver {
  int _idx = 0;

  @override
  void initState() {
    super.initState();
    WidgetsBinding.instance.addObserver(this);
    // Catch anything left over from a previous session.
    _sweepRecordings();
  }

  @override
  void dispose() {
    WidgetsBinding.instance.removeObserver(this);
    super.dispose();
  }

  @override
  void didChangeAppLifecycleState(AppLifecycleState state) {
    // Coming back from the dialer is exactly when a native call recording has
    // just finished being written. The post-call scan runs seconds after the
    // call and usually looks too early — OEM recorders finalise the file
    // later, and some not until their own app next runs — so this resume hook
    // is what actually collects most recordings.
    if (state == AppLifecycleState.resumed) _sweepRecordings();
  }

  void _sweepRecordings() {
    CallRecordingService.instance.sweepPending().then((count) {
      if (count > 0 && mounted) {
        ScaffoldMessenger.of(context).showSnackBar(
          SnackBar(
            content: Text('$count call recording(s) uploaded'),
            duration: const Duration(seconds: 2),
          ),
        );
      }
    }).catchError((_) {
      // Best-effort background work; never surface a failure here. The reason
      // is recorded on the service and shown in Profile.
    });
  }

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
          color: AppColors.surface,
          border: Border(top: BorderSide(color: AppColors.line, width: 1)),
        ),
        child: BottomNavigationBar(
          currentIndex: _idx,
          onTap: (i) {
            setState(() => _idx = i);
            context.go(tabs[i].path);
          },
          backgroundColor: AppColors.white,
          selectedItemColor: AppColors.brand,
          unselectedItemColor: AppColors.text3,
          type: BottomNavigationBarType.fixed,
          elevation: 0,
          items: tabs.asMap().entries.map((e) => BottomNavigationBarItem(
            icon: Padding(
              padding: const EdgeInsets.only(bottom: 3),
              child: AnimatedContainer(
                duration: const Duration(milliseconds: 140),
                curve: Curves.easeOut,
                padding: EdgeInsets.symmetric(
                  horizontal: _idx == e.key ? 14 : 0,
                  vertical: _idx == e.key ? 4 : 0,
                ),
                decoration: _idx == e.key
                    ? BoxDecoration(
                        color: AppColors.brand50,
                        borderRadius: BorderRadius.circular(999),
                      )
                    : null,
                child: Icon(_idx == e.key ? e.value.activeIcon : e.value.icon, size: 20),
              ),
            ),
            label: e.value.label,
          )).toList(),
          selectedLabelStyle: const TextStyle(fontFamily: 'Archivo', fontWeight: FontWeight.w700, fontSize: 10),
          unselectedLabelStyle: const TextStyle(fontFamily: 'Archivo', fontSize: 10),
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
class DialEasyproApp extends ConsumerStatefulWidget {
  const DialEasyproApp({super.key});

  @override
  ConsumerState<DialEasyproApp> createState() => _DialEasyproAppState();
}

class _DialEasyproAppState extends ConsumerState<DialEasyproApp>
    with WidgetsBindingObserver {
  /// Don't re-sync on every glance at the phone. Coming back from a ten
  /// second detour does not change what is scheduled.
  static const _minResyncGap = Duration(minutes: 10);
  DateTime? _lastSync;

  /// How often to ask whether the server has raised anything.
  ///
  /// Separate from the reminder re-sync above, and much more frequent: a
  /// follow-up someone books on your lead is news now, and with no push
  /// configured the only way this phone learns of it is by asking. Each ask
  /// costs one small unread-count request when there is nothing new.
  ///
  /// It keeps running while the app is in the background — that is the whole
  /// point, since an agent looking at the app does not need the shade — but
  /// more slowly, because there it is a background app spending someone's
  /// battery. Android freezing the process eventually stops it either way;
  /// the scheduled alarms are what survive that, and FCM is what would fix
  /// it properly (apps/authentication/push.py).
  static const _serverPollTick = Duration(minutes: 1);
  static const _foregroundPollGap = Duration(minutes: 1);
  static const _backgroundPollGap = Duration(minutes: 5);

  Timer? _serverPoll;
  DateTime? _lastServerPull;
  AppLifecycleState _lifecycle = AppLifecycleState.resumed;

  @override
  void initState() {
    super.initState();
    WidgetsBinding.instance.addObserver(this);
    _serverPoll = Timer.periodic(_serverPollTick, (_) => _pullServerNotifications());
  }

  @override
  void dispose() {
    _serverPoll?.cancel();
    WidgetsBinding.instance.removeObserver(this);
    super.dispose();
  }

  /// Raise anything the server has for this agent in the Android shade.
  ///
  /// Lives at app level rather than on the bell: the bell is only mounted on
  /// the dashboard, so an agent sitting on any other screen would be told
  /// nothing.
  void _pullServerNotifications({bool force = false}) {
    if (!ref.read(authProvider).isAuthenticated) return;

    final now = DateTime.now();
    final gap = _lifecycle == AppLifecycleState.resumed
        ? _foregroundPollGap
        : _backgroundPollGap;
    if (!force && _lastServerPull != null && now.difference(_lastServerPull!) < gap) {
      return;
    }
    _lastServerPull = now;

    unawaited(NotificationService.instance.syncServerNotifications());
  }

  @override
  void didChangeAppLifecycleState(AppLifecycleState state) {
    _lifecycle = state;
    if (state != AppLifecycleState.resumed) return;

    // Reminders were armed once, at login. An app left open for days keeps
    // firing alarms for follow-ups that have since been completed or moved,
    // and never learns about one scheduled from the web this morning.
    // Resuming is the natural moment to reconcile: it is when the agent is
    // about to look at their day anyway.
    if (!ref.read(authProvider).isAuthenticated) return;

    // Regardless of the gaps above: picking the phone up is the moment the
    // badge and the shade are most likely to be behind.
    _pullServerNotifications(force: true);

    final now = DateTime.now();
    if (_lastSync != null && now.difference(_lastSync!) < _minResyncGap) return;
    _lastSync = now;

    // Not awaited: a slow or failed sync must not hold up the first frame
    // after a resume. It logs its own failures.
    unawaited(NotificationService.instance.syncFollowupReminders());
  }

  @override
  Widget build(BuildContext context) {
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
