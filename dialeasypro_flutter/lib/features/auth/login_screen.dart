import 'package:flutter/material.dart';
import 'package:flutter_animate/flutter_animate.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:go_router/go_router.dart';
import '../../core/services/tenant_config.dart';
import '../../core/theme/colors.dart';
import '../../core/widgets/widgets.dart';
import '../../data/services/api_client.dart';
import 'auth_provider.dart';

class LoginScreen extends ConsumerStatefulWidget {
  const LoginScreen({super.key});

  @override
  ConsumerState<LoginScreen> createState() => _LoginScreenState();
}

class _LoginScreenState extends ConsumerState<LoginScreen> {
  final _workspaceCtrl = TextEditingController();
  final _emailCtrl = TextEditingController();
  final _passwordCtrl = TextEditingController();
  final _customUrlCtrl = TextEditingController();
  bool _showPassword = false;
  bool _loading = false;
  bool _testing = false;
  bool _showAdvanced = false;
  String? _workspaceError;

  @override
  void initState() {
    super.initState();
    // Pre-fill workspace from saved config
    _workspaceCtrl.text = TenantConfig.instance.tenantSlug ?? '';
    _customUrlCtrl.text = TenantConfig.useLocalApi ? '' : TenantConfig.instance.customBaseUrl ?? '';
    if (!TenantConfig.useLocalApi &&
        TenantConfig.instance.customBaseUrl != null &&
        TenantConfig.instance.customBaseUrl!.isNotEmpty) {
      _showAdvanced = true;
    }
  }

  @override
  void dispose() {
    _workspaceCtrl.dispose();
    _emailCtrl.dispose();
    _passwordCtrl.dispose();
    _customUrlCtrl.dispose();
    super.dispose();
  }

  Future<void> _submit() async {
    final workspace = _workspaceCtrl.text.trim();
    final customUrl = _customUrlCtrl.text.trim();
    final email = _emailCtrl.text.trim();
    final pw = _passwordCtrl.text;

    if (workspace.isEmpty) {
      setState(() => _workspaceError = 'Enter your company workspace');
      AppToast.show(context, 'Enter your company workspace', isError: true);
      return;
    }
    if (email.isEmpty || pw.isEmpty) {
      AppToast.show(context, 'Enter email and password', isError: true);
      return;
    }

    // Save tenant config first so API client uses it
    await TenantConfig.instance.save(slug: workspace, customUrl: customUrl);

    setState(() { _loading = true; _workspaceError = null; });
    final ok = await ref.read(authProvider.notifier).login(email.toLowerCase(), pw);
    if (!mounted) return;
    setState(() => _loading = false);
    if (ok) {
      context.go('/');
    } else {
      final err = ref.read(authProvider).error ?? 'Login failed';
      AppToast.show(context, err, isError: true);
      // If error suggests bad tenant, highlight workspace field
      if (err.toLowerCase().contains('connect') || err.toLowerCase().contains('workspace')) {
        setState(() => _workspaceError = err);
      }
    }
  }

  Future<void> _testConnection() async {
    final workspace = _workspaceCtrl.text.trim();
    final customUrl = _customUrlCtrl.text.trim();
    if (workspace.isEmpty) {
      AppToast.show(context, 'Enter workspace first', isError: true);
      return;
    }
    setState(() => _testing = true);
    await TenantConfig.instance.save(slug: workspace, customUrl: customUrl);
    final err = await ApiClient.instance.testTenantConnection();
    if (!mounted) return;
    setState(() {
      _testing = false;
      _workspaceError = err;
    });
    if (err == null) {
      AppToast.show(context, 'Connected ✓', isSuccess: true);
    } else {
      AppToast.show(context, err, isError: true);
    }
  }

  @override
  Widget build(BuildContext context) {
    final workspace = _workspaceCtrl.text.trim();
    final customUrl = _customUrlCtrl.text.trim();
    final resolvedUrl = TenantConfig.useLocalApi
        ? '${TenantConfig.defaultBaseUrl} as ${workspace.isEmpty ? 'your tenant' : workspace}'
        : customUrl.isNotEmpty
        ? customUrl.replaceAll(RegExp(r'/+$'), '')
        : workspace.isEmpty
            ? TenantConfig.defaultBaseUrl
            : workspace.startsWith('http://') || workspace.startsWith('https://')
                ? workspace.replaceAll(RegExp(r'/+$'), '')
                : workspace.contains('.')
                    ? 'https://$workspace'
                    : 'https://$workspace.${TenantConfig.defaultRootDomain}';

    return Scaffold(
      backgroundColor: AppColors.yellow,
      body: SafeArea(
        child: Stack(children: [
          Positioned.fill(child: CustomPaint(painter: _DotPainter())),
          SingleChildScrollView(
            padding: const EdgeInsets.symmetric(horizontal: 24, vertical: 24),
            child: ConstrainedBox(
              constraints: BoxConstraints(minHeight: MediaQuery.of(context).size.height - 48),
              child: Column(
                mainAxisAlignment: MainAxisAlignment.center,
                children: [
                  Container(
                    width: 72, height: 72,
                    decoration: BoxDecoration(
                      color: AppColors.black,
                      border: Border.all(color: AppColors.black, width: 2.5),
                      boxShadow: const [BoxShadow(color: AppColors.dark, offset: Offset(5, 5))],
                    ),
                    child: const Center(
                      child: Text('D',
                          style: TextStyle(fontFamily: 'SpaceGrotesk', fontWeight: FontWeight.w700, fontSize: 34, color: AppColors.yellow)),
                    ),
                  ).animate().scale(begin: const Offset(0.6, 0.6), duration: 500.ms, curve: Curves.easeOutBack),

                  const SizedBox(height: 14),
                  const Text('DialEasypro',
                      style: TextStyle(fontFamily: 'SpaceGrotesk', fontWeight: FontWeight.w700, fontSize: 28, color: AppColors.black, letterSpacing: -0.5))
                      .animate().fadeIn(delay: 200.ms),
                  const SizedBox(height: 2),
                  const Text('Auto-dialer CRM for Sales Closers',
                      style: TextStyle(fontFamily: 'DMSans', fontWeight: FontWeight.w500, fontSize: 12, color: AppColors.dark))
                      .animate().fadeIn(delay: 300.ms),

                  const SizedBox(height: 28),

                  Container(
                    decoration: BoxDecoration(
                      color: AppColors.white,
                      border: Border.all(color: AppColors.black, width: 2.5),
                      boxShadow: const [BoxShadow(color: AppColors.black, offset: Offset(7, 7))],
                    ),
                    child: Column(
                      crossAxisAlignment: CrossAxisAlignment.stretch,
                      children: [
                        Container(
                          padding: const EdgeInsets.symmetric(horizontal: 18, vertical: 13),
                          decoration: const BoxDecoration(
                            color: AppColors.dark,
                            border: Border(bottom: BorderSide(color: AppColors.black, width: 2)),
                          ),
                          child: Column(
                            crossAxisAlignment: CrossAxisAlignment.start,
                            children: const [
                              Text('Sign in to your Workspace',
                                  style: TextStyle(fontFamily: 'SpaceGrotesk', fontWeight: FontWeight.w700, fontSize: 16, color: AppColors.yellow)),
                              SizedBox(height: 2),
                              Text('Enter your workspace and credentials.',
                                  style: TextStyle(fontFamily: 'DMSans', fontSize: 11, color: AppColors.muted)),
                            ],
                          ),
                        ),
                        Padding(
                          padding: const EdgeInsets.all(18),
                          child: Column(children: [
                            // ─── Workspace field ─────────────────
                            _WorkspaceField(
                              controller: _workspaceCtrl,
                              rootDomain: TenantConfig.defaultRootDomain,
                              defaultBaseUrl: TenantConfig.defaultBaseUrl,
                              errorText: _workspaceError,
                              onChanged: (v) {
                                if (_workspaceError != null) setState(() => _workspaceError = null);
                                setState((){}); // refresh URL preview
                              },
                              advancedOpen: _showAdvanced,
                              onToggleAdvanced: () => setState(() => _showAdvanced = !_showAdvanced),
                            ),

                            if (_showAdvanced) ...[
                              const SizedBox(height: 10),
                              BrutalTextField(
                                label: 'Custom API URL (optional)',
                                hint: TenantConfig.defaultBaseUrl,
                                controller: _customUrlCtrl,
                                keyboardType: TextInputType.url,
                                prefixIcon: Icons.dns_outlined,
                                onChanged: (_) => setState((){}),
                              ),
                              const SizedBox(height: 8),
                              Row(children: [
                                Expanded(child: Container(
                                  padding: const EdgeInsets.symmetric(horizontal: 8, vertical: 6),
                                  decoration: BoxDecoration(
                                    color: AppColors.greyLight,
                                    border: Border.all(color: AppColors.black, width: 1),
                                  ),
                                  child: Text(
                                    'Resolves to: $resolvedUrl',
                                    style: const TextStyle(fontFamily: 'monospace', fontSize: 10, color: AppColors.greyDark),
                                    overflow: TextOverflow.ellipsis,
                                  ),
                                )),
                                const SizedBox(width: 8),
                                BrutalButton.secondary(
                                  label: _testing ? 'Testing…' : 'Test',
                                  isFullWidth: false,
                                  padding: const EdgeInsets.symmetric(horizontal: 10, vertical: 6),
                                  isLoading: _testing,
                                  onPressed: _testing ? null : _testConnection,
                                ),
                              ]),
                            ],

                            const SizedBox(height: 14),
                            const Divider(thickness: 1, color: AppColors.greyLight),
                            const SizedBox(height: 14),

                            BrutalTextField(
                              label: 'Email',
                              hint: 'agent@yourcompany.com',
                              controller: _emailCtrl,
                              keyboardType: TextInputType.emailAddress,
                              textInputAction: TextInputAction.next,
                              prefixIcon: Icons.mail_outline,
                            ),
                            const SizedBox(height: 12),
                            BrutalTextField(
                              label: 'Password',
                              hint: '••••••••',
                              controller: _passwordCtrl,
                              obscureText: !_showPassword,
                              textInputAction: TextInputAction.done,
                              prefixIcon: Icons.lock_outline,
                              suffix: IconButton(
                                icon: Icon(_showPassword ? Icons.visibility_off_outlined : Icons.visibility_outlined, size: 20, color: AppColors.grey),
                                onPressed: () => setState(() => _showPassword = !_showPassword),
                              ),
                              onSubmitted: (_) => _submit(),
                            ),
                            const SizedBox(height: 20),
                            BrutalButton.primary(
                              label: _loading ? 'Signing in…' : 'SIGN IN →',
                              isLoading: _loading,
                              onPressed: _loading ? null : _submit,
                            ),
                          ]),
                        ),
                      ],
                    ),
                  ).animate().slideY(begin: 0.15, end: 0, delay: 200.ms, duration: 450.ms, curve: Curves.easeOut).fadeIn(delay: 200.ms),

                  const SizedBox(height: 18),

                  Container(
                    padding: const EdgeInsets.all(10),
                    decoration: BoxDecoration(
                      color: AppColors.dark,
                      border: Border.all(color: AppColors.black, width: 2),
                      boxShadow: const [BoxShadow(color: AppColors.black, offset: Offset(3, 3))],
                    ),
                    child: const Row(mainAxisSize: MainAxisSize.min, children: [
                      Text('⚡', style: TextStyle(fontSize: 13)),
                      SizedBox(width: 7),
                      Text("Don't know your workspace? Ask your admin.",
                          style: TextStyle(fontFamily: 'DMSans', fontSize: 10, color: AppColors.muted)),
                    ]),
                  ).animate().fadeIn(delay: 500.ms),
                ],
              ),
            ),
          ),
        ]),
      ),
    );
  }
}

// ─── Workspace Field with subdomain preview ──────────────────
class _WorkspaceField extends StatelessWidget {
  final TextEditingController controller;
  final String rootDomain;
  final String defaultBaseUrl;
  final String? errorText;
  final ValueChanged<String> onChanged;
  final bool advancedOpen;
  final VoidCallback onToggleAdvanced;

  const _WorkspaceField({
    required this.controller,
    required this.rootDomain,
    required this.defaultBaseUrl,
    required this.errorText,
    required this.onChanged,
    required this.advancedOpen,
    required this.onToggleAdvanced,
  });

  @override
  Widget build(BuildContext context) {
    return Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
      Row(children: [
        const Expanded(child: Text('WORKSPACE',
            style: TextStyle(fontFamily: 'SpaceGrotesk', fontWeight: FontWeight.w700, fontSize: 10, letterSpacing: 0.8, color: AppColors.greyDark))),
        GestureDetector(
          onTap: onToggleAdvanced,
          child: Text(
            advancedOpen ? '× Hide advanced' : '⚙ Advanced',
            style: const TextStyle(fontFamily: 'SpaceGrotesk', fontWeight: FontWeight.w700, fontSize: 10, color: AppColors.info, decoration: TextDecoration.underline),
          ),
        ),
      ]),
      const SizedBox(height: 6),
      Container(
        decoration: BoxDecoration(
          color: AppColors.white,
          border: Border.all(color: errorText != null ? AppColors.error : AppColors.black, width: 2),
          boxShadow: [BoxShadow(color: errorText != null ? AppColors.error : AppColors.black, offset: const Offset(3, 3))],
        ),
        child: Row(children: [
          const Padding(
            padding: EdgeInsets.only(left: 12, right: 4),
            child: Icon(Icons.business_outlined, size: 18, color: AppColors.grey),
          ),
          Expanded(
            child: TextField(
              controller: controller,
              onChanged: onChanged,
              textInputAction: TextInputAction.next,
              autocorrect: false,
              enableSuggestions: false,
              style: const TextStyle(fontFamily: 'DMSans', fontSize: 14, color: AppColors.black, fontWeight: FontWeight.w500),
              decoration: const InputDecoration(
                hintText: 'demo or demo.url.com',
                hintStyle: TextStyle(fontFamily: 'DMSans', color: AppColors.grey, fontSize: 14),
                border: InputBorder.none,
                contentPadding: EdgeInsets.symmetric(horizontal: 4, vertical: 14),
              ),
            ),
          ),
          // Domain suffix hint. Always show the short ".rootDomain" (never the
          // full URL) and cap its width so it can't squeeze out the input box
          // on narrow screens. The full resolved URL is shown under Advanced.
          ConstrainedBox(
            constraints: const BoxConstraints(maxWidth: 130),
            child: Container(
              margin: const EdgeInsets.symmetric(vertical: 6, horizontal: 6),
              padding: const EdgeInsets.symmetric(horizontal: 8, vertical: 6),
              decoration: BoxDecoration(
                color: AppColors.greyLight,
                border: Border.all(color: AppColors.greyDark, width: 1),
              ),
              child: Text(
                '.$rootDomain',
                maxLines: 1,
                overflow: TextOverflow.ellipsis,
                style: const TextStyle(fontFamily: 'monospace', fontWeight: FontWeight.w600, fontSize: 11, color: AppColors.greyDark),
              ),
            ),
          ),
        ]),
      ),
      if (errorText != null) Padding(
        padding: const EdgeInsets.only(top: 4),
        child: Row(children: [
          const Icon(Icons.error_outline, size: 12, color: AppColors.error),
          const SizedBox(width: 4),
          Expanded(child: Text(errorText!, style: const TextStyle(fontFamily: 'DMSans', fontSize: 11, color: AppColors.error))),
        ]),
      ),
    ]);
  }
}

class _DotPainter extends CustomPainter {
  @override
  void paint(Canvas canvas, Size size) {
    final paint = Paint()..color = AppColors.black.withValues(alpha: 0.07)..style = PaintingStyle.fill;
    const spacing = 22.0;
    for (double x = 0; x < size.width; x += spacing) {
      for (double y = 0; y < size.height; y += spacing) {
        canvas.drawCircle(Offset(x, y), 1.5, paint);
      }
    }
  }
  @override bool shouldRepaint(_) => false;
}
