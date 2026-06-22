import 'package:flutter/material.dart';
import 'package:flutter/services.dart';
import 'package:flutter_animate/flutter_animate.dart';
import '../theme/colors.dart';

// ============================================================
// DialEasypro — Polished UI Widget Library
// ============================================================

// ─── BRUTAL CARD ────────────────────────────────────────────
class BrutalCard extends StatefulWidget {
  final Widget child;
  final EdgeInsetsGeometry? padding;
  final Color? color;
  final Color? borderColor;
  final double shadowOffset;
  final Color shadowColor;
  final VoidCallback? onTap;
  final VoidCallback? onLongPress;
  final BorderRadius? borderRadius;
  final double borderWidth;

  const BrutalCard({
    super.key,
    required this.child,
    this.padding,
    this.color,
    this.borderColor,
    this.shadowOffset = 4,
    this.shadowColor = AppColors.black,
    this.onTap,
    this.onLongPress,
    this.borderRadius,
    this.borderWidth = 2,
  });

  @override
  State<BrutalCard> createState() => _BrutalCardState();
}

class _BrutalCardState extends State<BrutalCard> {
  bool _pressed = false;

  @override
  Widget build(BuildContext context) {
    final hasTap = widget.onTap != null || widget.onLongPress != null;

    final card = AnimatedContainer(
      duration: const Duration(milliseconds: 90),
      transform: Matrix4.translationValues(
        _pressed ? widget.shadowOffset / 2 : 0,
        _pressed ? widget.shadowOffset / 2 : 0,
        0,
      ),
      decoration: BoxDecoration(
        color: widget.color ?? AppColors.white,
        border: Border.all(color: widget.borderColor ?? AppColors.black, width: widget.borderWidth),
        borderRadius: widget.borderRadius,
        boxShadow: [
          BoxShadow(
            color: widget.shadowColor,
            offset: Offset(
              _pressed ? widget.shadowOffset / 2 : widget.shadowOffset,
              _pressed ? widget.shadowOffset / 2 : widget.shadowOffset,
            ),
          ),
        ],
      ),
      child: widget.padding != null ? Padding(padding: widget.padding!, child: widget.child) : widget.child,
    );

    if (!hasTap) return card;
    return GestureDetector(
      onTap: () { HapticFeedback.lightImpact(); widget.onTap?.call(); },
      onLongPress: widget.onLongPress,
      onTapDown: (_) => setState(() => _pressed = true),
      onTapUp: (_) => setState(() => _pressed = false),
      onTapCancel: () => setState(() => _pressed = false),
      child: card,
    );
  }
}

// ─── BRUTAL BUTTON ──────────────────────────────────────────
class BrutalButton extends StatefulWidget {
  final String label;
  final VoidCallback? onPressed;
  final Color? backgroundColor;
  final Color? textColor;
  final bool isLoading;
  final bool isFullWidth;
  final Widget? icon;
  final IconData? iconData;
  final double? fontSize;
  final EdgeInsetsGeometry? padding;
  final double shadowOffset;
  final LinearGradient? gradient;

  const BrutalButton({
    super.key,
    required this.label,
    this.onPressed,
    this.backgroundColor,
    this.textColor,
    this.isLoading = false,
    this.isFullWidth = false,
    this.icon,
    this.iconData,
    this.fontSize,
    this.padding,
    this.shadowOffset = 4,
    this.gradient,
  });

  // Variants
  const BrutalButton.primary({
    super.key, required this.label, this.onPressed,
    this.isLoading = false, this.isFullWidth = true,
    this.icon, this.iconData, this.fontSize, this.padding, this.shadowOffset = 5,
  }) : backgroundColor = AppColors.black, textColor = AppColors.white, gradient = null;

  const BrutalButton.secondary({
    super.key, required this.label, this.onPressed,
    this.isLoading = false, this.isFullWidth = false,
    this.icon, this.iconData, this.fontSize, this.padding, this.shadowOffset = 3,
  }) : backgroundColor = AppColors.white, textColor = AppColors.black, gradient = null;

  const BrutalButton.yellow({
    super.key, required this.label, this.onPressed,
    this.isLoading = false, this.isFullWidth = false,
    this.icon, this.iconData, this.fontSize, this.padding, this.shadowOffset = 4,
  }) : backgroundColor = AppColors.yellow, textColor = AppColors.black, gradient = null;

  const BrutalButton.success({
    super.key, required this.label, this.onPressed,
    this.isLoading = false, this.isFullWidth = false,
    this.icon, this.iconData, this.fontSize, this.padding, this.shadowOffset = 4,
  }) : backgroundColor = AppColors.success, textColor = AppColors.white, gradient = null;

  const BrutalButton.danger({
    super.key, required this.label, this.onPressed,
    this.isLoading = false, this.isFullWidth = false,
    this.icon, this.iconData, this.fontSize, this.padding, this.shadowOffset = 3,
  }) : backgroundColor = AppColors.error, textColor = AppColors.white, gradient = null;

  @override
  State<BrutalButton> createState() => _BrutalButtonState();
}

class _BrutalButtonState extends State<BrutalButton> {
  bool _pressed = false;

  @override
  Widget build(BuildContext context) {
    final disabled = widget.onPressed == null || widget.isLoading;
    final bg = widget.backgroundColor ?? AppColors.black;
    final fg = widget.textColor ?? AppColors.white;

    return GestureDetector(
      onTapDown: disabled ? null : (_) { setState(() => _pressed = true); HapticFeedback.selectionClick(); },
      onTapUp: disabled ? null : (_) => setState(() => _pressed = false),
      onTapCancel: () => setState(() => _pressed = false),
      onTap: disabled ? null : widget.onPressed,
      child: AnimatedContainer(
        duration: const Duration(milliseconds: 80),
        width: widget.isFullWidth ? double.infinity : null,
        transform: Matrix4.translationValues(
          _pressed ? widget.shadowOffset / 1.5 : 0,
          _pressed ? widget.shadowOffset / 1.5 : 0, 0,
        ),
        decoration: BoxDecoration(
          color: widget.gradient == null ? (disabled ? AppColors.greyLight : bg) : null,
          gradient: widget.gradient,
          border: Border.all(color: AppColors.black, width: 2),
          boxShadow: disabled ? [] : [BoxShadow(
            color: AppColors.black,
            offset: Offset(
              _pressed ? widget.shadowOffset / 3 : widget.shadowOffset,
              _pressed ? widget.shadowOffset / 3 : widget.shadowOffset,
            ),
          )],
        ),
        padding: widget.padding ?? const EdgeInsets.symmetric(horizontal: 20, vertical: 13),
        child: widget.isLoading
            ? SizedBox(
                height: 18,
                child: Center(
                  child: SizedBox(
                    width: 18, height: 18,
                    child: CircularProgressIndicator(strokeWidth: 2.5, color: fg),
                  ),
                ),
              )
            : Row(
                mainAxisSize: widget.isFullWidth ? MainAxisSize.max : MainAxisSize.min,
                mainAxisAlignment: MainAxisAlignment.center,
                children: [
                  if (widget.icon != null) ...[widget.icon!, const SizedBox(width: 8)],
                  if (widget.iconData != null) ...[
                    Icon(widget.iconData, size: 16, color: disabled ? AppColors.grey : fg),
                    const SizedBox(width: 6),
                  ],
                  Flexible(
                    child: Text(
                      widget.label,
                      style: TextStyle(
                        fontFamily: 'SpaceGrotesk',
                        fontWeight: FontWeight.w700,
                        fontSize: widget.fontSize ?? 14,
                        color: disabled ? AppColors.grey : fg,
                        letterSpacing: 0.3,
                      ),
                      overflow: TextOverflow.ellipsis,
                    ),
                  ),
                ],
              ),
      ),
    );
  }
}

// ─── BRUTAL TEXT FIELD ──────────────────────────────────────
class BrutalTextField extends StatefulWidget {
  final String? label;
  final String? hint;
  final TextEditingController? controller;
  final bool obscureText;
  final TextInputType? keyboardType;
  final TextInputAction? textInputAction;
  final ValueChanged<String>? onChanged;
  final ValueChanged<String>? onSubmitted;
  final VoidCallback? onTap;
  final String? errorText;
  final Widget? suffix;
  final Widget? prefix;
  final IconData? prefixIcon;
  final int? maxLines;
  final int? minLines;
  final int? maxLength;
  final bool readOnly;
  final bool autofocus;
  final FocusNode? focusNode;
  final String? Function(String?)? validator;

  const BrutalTextField({
    super.key,
    this.label, this.hint, this.controller,
    this.obscureText = false, this.keyboardType, this.textInputAction,
    this.onChanged, this.onSubmitted, this.onTap,
    this.errorText, this.suffix, this.prefix, this.prefixIcon,
    this.maxLines = 1, this.minLines, this.maxLength,
    this.readOnly = false, this.autofocus = false,
    this.focusNode, this.validator,
  });

  @override
  State<BrutalTextField> createState() => _BrutalTextFieldState();
}

class _BrutalTextFieldState extends State<BrutalTextField> {
  bool _focused = false;
  late final FocusNode _node;

  @override
  void initState() {
    super.initState();
    _node = widget.focusNode ?? FocusNode();
    _node.addListener(() => setState(() => _focused = _node.hasFocus));
  }

  @override
  Widget build(BuildContext context) {
    return Column(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        if (widget.label != null) ...[
          Text(widget.label!.toUpperCase(), style: AppTextStyles.label),
          const SizedBox(height: 6),
        ],
        AnimatedContainer(
          duration: const Duration(milliseconds: 120),
          decoration: BoxDecoration(
            color: AppColors.white,
            border: Border.all(
              color: widget.errorText != null
                  ? AppColors.error
                  : _focused
                      ? AppColors.yellow
                      : AppColors.black,
              width: _focused ? 2.5 : 2,
            ),
            boxShadow: [
              BoxShadow(
                color: widget.errorText != null
                    ? AppColors.error
                    : _focused
                        ? AppColors.yellow
                        : AppColors.black,
                offset: const Offset(3, 3),
              ),
            ],
          ),
          child: TextFormField(
            controller: widget.controller,
            obscureText: widget.obscureText,
            keyboardType: widget.keyboardType,
            textInputAction: widget.textInputAction,
            onChanged: widget.onChanged,
            onFieldSubmitted: widget.onSubmitted,
            onTap: widget.onTap,
            maxLines: widget.obscureText ? 1 : widget.maxLines,
            minLines: widget.minLines,
            maxLength: widget.maxLength,
            readOnly: widget.readOnly,
            focusNode: _node,
            autofocus: widget.autofocus,
            validator: widget.validator,
            style: const TextStyle(fontFamily: 'DMSans', fontSize: 14, color: AppColors.black),
            decoration: InputDecoration(
              hintText: widget.hint,
              hintStyle: const TextStyle(fontFamily: 'DMSans', color: AppColors.grey, fontSize: 14),
              suffixIcon: widget.suffix,
              prefixIcon: widget.prefix ?? (widget.prefixIcon != null
                  ? Icon(widget.prefixIcon, size: 18, color: AppColors.grey)
                  : null),
              border: InputBorder.none,
              enabledBorder: InputBorder.none,
              focusedBorder: InputBorder.none,
              errorBorder: InputBorder.none,
              contentPadding: const EdgeInsets.symmetric(horizontal: 14, vertical: 14),
              counterText: '',
            ),
          ),
        ),
        if (widget.errorText != null) ...[
          const SizedBox(height: 4),
          Row(children: [
            const Icon(Icons.error_outline, size: 12, color: AppColors.error),
            const SizedBox(width: 4),
            Text(widget.errorText!, style: const TextStyle(fontFamily: 'DMSans', fontSize: 11, color: AppColors.error)),
          ]),
        ],
      ],
    );
  }
}

// ─── STATUS BADGE (color-coded) ─────────────────────────────
class StatusBadge extends StatelessWidget {
  final String status;
  final String? label;
  final bool large;
  const StatusBadge({super.key, required this.status, this.label, this.large = false});

  @override
  Widget build(BuildContext context) {
    final cs = AppColors.leadStatusColors[status.toLowerCase()];
    final text = (label ?? status.replaceAll('_', ' ')).toUpperCase();
    return Container(
      padding: EdgeInsets.symmetric(horizontal: large ? 10 : 8, vertical: large ? 4 : 3),
      decoration: BoxDecoration(
        color: cs?.background ?? AppColors.greyLight,
        border: Border.all(color: cs?.border ?? AppColors.grey, width: 1.5),
      ),
      child: Text(
        text,
        style: TextStyle(
          fontFamily: 'SpaceGrotesk',
          fontWeight: FontWeight.w700,
          fontSize: large ? 11 : 9.5,
          letterSpacing: 0.5,
          color: cs?.text ?? AppColors.greyDark,
        ),
      ),
    );
  }
}

// ─── PRIORITY BADGE ─────────────────────────────────────────
class PriorityBadge extends StatelessWidget {
  final String priority;
  const PriorityBadge({super.key, required this.priority});

  @override
  Widget build(BuildContext context) {
    final color = AppColors.priorityColors[priority.toLowerCase()] ?? AppColors.grey;
    final isLight = priority == 'medium' || priority == 'low';
    return Container(
      padding: const EdgeInsets.symmetric(horizontal: 7, vertical: 2.5),
      decoration: BoxDecoration(
        color: color,
        border: Border.all(color: AppColors.black, width: 1.5),
      ),
      child: Row(
        mainAxisSize: MainAxisSize.min,
        children: [
          if (priority == 'hot') const Padding(
            padding: EdgeInsets.only(right: 2),
            child: Text('🔥', style: TextStyle(fontSize: 10)),
          ),
          Text(
            priority.toUpperCase(),
            style: TextStyle(
              fontFamily: 'SpaceGrotesk', fontWeight: FontWeight.w700, fontSize: 9.5,
              letterSpacing: 0.4, color: isLight ? AppColors.black : AppColors.white,
            ),
          ),
        ],
      ),
    );
  }
}

// ─── SCORE BAR (animated) ───────────────────────────────────
class ScoreBar extends StatelessWidget {
  final int score;
  final bool showLabel;
  const ScoreBar({super.key, required this.score, this.showLabel = true});

  @override
  Widget build(BuildContext context) {
    final color = score >= 70 ? AppColors.success
                : score >= 40 ? AppColors.warning : AppColors.error;
    return Row(mainAxisSize: MainAxisSize.min, children: [
      Container(
        width: 56, height: 8,
        decoration: BoxDecoration(
          color: AppColors.greyLight,
          border: Border.all(color: AppColors.black, width: 1.5),
        ),
        child: FractionallySizedBox(
          alignment: Alignment.centerLeft,
          widthFactor: score.clamp(0, 100) / 100,
          child: Container(color: color),
        ),
      ),
      if (showLabel) ...[
        const SizedBox(width: 4),
        Text('$score', style: const TextStyle(
          fontFamily: 'monospace', fontSize: 11, fontWeight: FontWeight.w600, color: AppColors.greyDark,
        )),
      ],
    ]);
  }
}

// ─── TAG CHIP ────────────────────────────────────────────────
class TagChip extends StatelessWidget {
  final String label;
  final Color? backgroundColor;
  final Color? textColor;
  final IconData? icon;
  final VoidCallback? onTap;

  const TagChip({
    super.key, required this.label,
    this.backgroundColor, this.textColor, this.icon, this.onTap,
  });

  @override
  Widget build(BuildContext context) {
    final w = Container(
      padding: const EdgeInsets.symmetric(horizontal: 7, vertical: 3),
      decoration: BoxDecoration(
        color: backgroundColor ?? AppColors.yellow,
        border: Border.all(color: AppColors.black, width: 1.5),
      ),
      child: Row(
        mainAxisSize: MainAxisSize.min,
        children: [
          if (icon != null) ...[
            Icon(icon, size: 10, color: textColor ?? AppColors.black),
            const SizedBox(width: 4),
          ],
          Text(
            label.toUpperCase(),
            style: TextStyle(
              fontFamily: 'SpaceGrotesk', fontWeight: FontWeight.w700, fontSize: 9,
              letterSpacing: 0.4, color: textColor ?? AppColors.black,
            ),
          ),
        ],
      ),
    );
    if (onTap == null) return w;
    return GestureDetector(onTap: onTap, child: w);
  }
}

// ─── STAT CARD (more colorful) ──────────────────────────────
class StatCard extends StatelessWidget {
  final String label;
  final String value;
  final String? sub;
  final IconData? icon;
  final Color? accentColor;
  final VoidCallback? onTap;

  const StatCard({
    super.key,
    required this.label,
    required this.value,
    this.sub,
    this.icon,
    this.accentColor,
    this.onTap,
  });

  @override
  Widget build(BuildContext context) {
    return BrutalCard(
      onTap: onTap,
      padding: const EdgeInsets.all(14),
      color: AppColors.white,
      shadowOffset: 4,
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Row(
            mainAxisAlignment: MainAxisAlignment.spaceBetween,
            children: [
              Flexible(child: Text(label.toUpperCase(), style: AppTextStyles.label)),
              if (icon != null)
                Container(
                  padding: const EdgeInsets.all(4),
                  decoration: BoxDecoration(
                    color: (accentColor ?? AppColors.yellow).withOpacity(0.2),
                    border: Border.all(color: accentColor ?? AppColors.black, width: 1.5),
                  ),
                  child: Icon(icon, size: 13, color: accentColor ?? AppColors.dark),
                ),
            ],
          ),
          const SizedBox(height: 8),
          Text(value, style: AppTextStyles.h2),
          if (sub != null) ...[
            const SizedBox(height: 2),
            Text(sub!, style: AppTextStyles.caption),
          ],
        ],
      ),
    );
  }
}

// ─── COMPACT KPI (for dashboard small) ──────────────────────
class CompactKpi extends StatelessWidget {
  final String label;
  final String value;
  final Color color;
  final IconData icon;
  const CompactKpi({super.key, required this.label, required this.value, required this.color, required this.icon});

  @override
  Widget build(BuildContext context) {
    return Container(
      padding: const EdgeInsets.all(12),
      decoration: BoxDecoration(
        // Composite the tint over white so the fill is fully OPAQUE. A bare
        // color.withOpacity(0.12) is translucent and lets a dark surface behind
        // it bleed through, making the card look black and hiding the text.
        color: Color.alphaBlend(color.withOpacity(0.12), AppColors.white),
        border: Border.all(color: color, width: 2),
        boxShadow: const [BoxShadow(color: AppColors.black, offset: Offset(3, 3))],
      ),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Icon(icon, size: 16, color: color),
          const SizedBox(height: 6),
          Text(value, style: TextStyle(fontFamily: 'SpaceGrotesk', fontWeight: FontWeight.w700, fontSize: 18, color: AppColors.black)),
          Text(label, style: const TextStyle(fontFamily: 'DMSans', fontSize: 10, color: AppColors.grey)),
        ],
      ),
    );
  }
}

// ─── INFO ROW ───────────────────────────────────────────────
class InfoRow extends StatelessWidget {
  final String label;
  final String value;
  final IconData? icon;
  final VoidCallback? onTap;

  const InfoRow({super.key, required this.label, required this.value, this.icon, this.onTap});

  @override
  Widget build(BuildContext context) {
    return Padding(
      padding: const EdgeInsets.symmetric(vertical: 8),
      child: Row(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          if (icon != null) ...[
            Icon(icon, size: 14, color: AppColors.grey),
            const SizedBox(width: 8),
          ],
          Expanded(
            flex: 2,
            child: Text(label.toUpperCase(), style: AppTextStyles.label),
          ),
          Expanded(
            flex: 3,
            child: onTap != null
                ? GestureDetector(
                    onTap: onTap,
                    child: Text(value, style: AppTextStyles.bodyMedium.copyWith(decoration: TextDecoration.underline)),
                  )
                : Text(value, style: AppTextStyles.bodyMedium),
          ),
        ],
      ),
    );
  }
}

// ─── EMPTY STATE ────────────────────────────────────────────
class EmptyStateView extends StatelessWidget {
  final IconData icon;
  final String title;
  final String? message;
  final String? buttonLabel;
  final VoidCallback? onAction;
  final Color? iconColor;

  const EmptyStateView({
    super.key, required this.icon, required this.title,
    this.message, this.buttonLabel, this.onAction, this.iconColor,
  });

  @override
  Widget build(BuildContext context) {
    return Center(
      child: SingleChildScrollView(
        padding: const EdgeInsets.all(32),
        child: Column(
          mainAxisSize: MainAxisSize.min,
          children: [
            Container(
              padding: const EdgeInsets.all(20),
              decoration: BoxDecoration(
                color: (iconColor ?? AppColors.yellow).withOpacity(0.18),
                border: Border.all(color: iconColor ?? AppColors.black, width: 2),
                boxShadow: const [BoxShadow(color: AppColors.black, offset: Offset(4, 4))],
              ),
              child: Icon(icon, size: 40, color: iconColor ?? AppColors.dark),
            ).animate().scale(begin: const Offset(0.7, 0.7), duration: 400.ms, curve: Curves.easeOutBack),
            const SizedBox(height: 20),
            Text(title, style: AppTextStyles.h3, textAlign: TextAlign.center),
            if (message != null) ...[
              const SizedBox(height: 8),
              Text(message!, style: AppTextStyles.body.copyWith(color: AppColors.grey), textAlign: TextAlign.center),
            ],
            if (buttonLabel != null && onAction != null) ...[
              const SizedBox(height: 24),
              BrutalButton.primary(label: buttonLabel!, onPressed: onAction, isFullWidth: false),
            ],
          ],
        ),
      ),
    );
  }
}

// ─── SHIMMER ────────────────────────────────────────────────
class ShimmerCard extends StatelessWidget {
  final double height;
  final double? width;
  const ShimmerCard({super.key, this.height = 100, this.width});

  @override
  Widget build(BuildContext context) {
    return Container(
      width: width ?? double.infinity,
      height: height,
      decoration: BoxDecoration(
        color: AppColors.greyLight,
        border: Border.all(color: AppColors.black, width: 2),
        boxShadow: const [BoxShadow(color: AppColors.black, offset: Offset(4, 4))],
      ),
    ).animate(onPlay: (c) => c.repeat(reverse: true)).fade(begin: 1, end: 0.6, duration: 800.ms);
  }
}

// ─── REFRESH INDICATOR ──────────────────────────────────────
class BrutalRefreshIndicator extends StatelessWidget {
  final Widget child;
  final Future<void> Function() onRefresh;
  const BrutalRefreshIndicator({super.key, required this.child, required this.onRefresh});

  @override
  Widget build(BuildContext context) => RefreshIndicator(
    onRefresh: onRefresh,
    color: AppColors.black,
    backgroundColor: AppColors.yellow,
    strokeWidth: 2.5,
    child: child,
  );
}

// ─── TOAST ─────────────────────────────────────────────────
class AppToast {
  static void show(BuildContext context, String message, {
    bool isError = false, bool isSuccess = false, bool isInfo = false,
  }) {
    HapticFeedback.lightImpact();
    final color = isError ? AppColors.error : isSuccess ? AppColors.success : isInfo ? AppColors.info : AppColors.yellow;
    final icon = isError ? Icons.error_outline : isSuccess ? Icons.check_circle_outline : Icons.info_outline;
    ScaffoldMessenger.of(context).hideCurrentSnackBar();
    ScaffoldMessenger.of(context).showSnackBar(SnackBar(
      content: Row(children: [
        Icon(icon, color: color, size: 18),
        const SizedBox(width: 10),
        Expanded(child: Text(message, style: const TextStyle(fontFamily: 'DMSans', color: AppColors.white, fontSize: 13))),
      ]),
      backgroundColor: AppColors.dark,
      behavior: SnackBarBehavior.floating,
      margin: const EdgeInsets.all(16),
      padding: const EdgeInsets.symmetric(horizontal: 14, vertical: 12),
      shape: const RoundedRectangleBorder(
        borderRadius: BorderRadius.zero,
        side: BorderSide(color: AppColors.black, width: 2),
      ),
      duration: const Duration(seconds: 3),
    ));
  }
}

// ─── BOTTOM SHEET ───────────────────────────────────────────
Future<T?> showBrutalBottomSheet<T>({
  required BuildContext context,
  required Widget Function(BuildContext) builder,
  bool isScrollControlled = true,
  Color? backgroundColor,
}) => showModalBottomSheet<T>(
  context: context,
  isScrollControlled: isScrollControlled,
  backgroundColor: backgroundColor ?? AppColors.white,
  shape: const RoundedRectangleBorder(
    borderRadius: BorderRadius.zero,
    side: BorderSide(color: AppColors.black, width: 2),
  ),
  builder: (ctx) => Padding(
    padding: EdgeInsets.only(bottom: MediaQuery.of(ctx).viewInsets.bottom),
    child: builder(ctx),
  ),
);

// ─── CONFIRM DIALOG ─────────────────────────────────────────
Future<bool?> showBrutalConfirm({
  required BuildContext context,
  required String title,
  required String message,
  String confirmLabel = 'Confirm',
  bool danger = false,
}) => showDialog<bool>(
  context: context,
  builder: (ctx) => Dialog(
    insetPadding: const EdgeInsets.all(20),
    shape: const RoundedRectangleBorder(
      borderRadius: BorderRadius.zero,
      side: BorderSide(color: AppColors.black, width: 2),
    ),
    child: Column(
      mainAxisSize: MainAxisSize.min,
      crossAxisAlignment: CrossAxisAlignment.stretch,
      children: [
        Container(
          padding: const EdgeInsets.all(16),
          decoration: BoxDecoration(
            color: danger ? AppColors.error : AppColors.dark,
            border: const Border(bottom: BorderSide(color: AppColors.black, width: 2)),
          ),
          child: Text(
            title,
            style: const TextStyle(fontFamily: 'SpaceGrotesk', fontWeight: FontWeight.w700, fontSize: 16, color: AppColors.white),
          ),
        ),
        Padding(
          padding: const EdgeInsets.all(20),
          child: Text(message, style: AppTextStyles.body),
        ),
        Padding(
          padding: const EdgeInsets.fromLTRB(20, 0, 20, 20),
          child: Row(children: [
            Expanded(child: BrutalButton.secondary(label: 'Cancel', isFullWidth: true, onPressed: () => Navigator.pop(ctx, false))),
            const SizedBox(width: 12),
            Expanded(child: BrutalButton(
              label: confirmLabel, isFullWidth: true,
              backgroundColor: danger ? AppColors.error : AppColors.black,
              textColor: AppColors.white,
              onPressed: () => Navigator.pop(ctx, true),
            )),
          ]),
        ),
      ],
    ),
  ),
);

// ─── SECTION HEADER ─────────────────────────────────────────
class SectionHeader extends StatelessWidget {
  final String title;
  final String? subtitle;
  final Widget? action;
  final IconData? icon;

  const SectionHeader({super.key, required this.title, this.subtitle, this.action, this.icon});

  @override
  Widget build(BuildContext context) {
    return Row(
      children: [
        if (icon != null) ...[
          Container(
            padding: const EdgeInsets.all(6),
            decoration: BoxDecoration(
              color: AppColors.yellow,
              border: Border.all(color: AppColors.black, width: 1.5),
            ),
            child: Icon(icon, size: 14, color: AppColors.black),
          ),
          const SizedBox(width: 10),
        ],
        Expanded(
          child: Column(
            crossAxisAlignment: CrossAxisAlignment.start,
            children: [
              Text(title, style: AppTextStyles.h3),
              if (subtitle != null) Text(subtitle!, style: AppTextStyles.caption),
            ],
          ),
        ),
        if (action != null) action!,
      ],
    );
  }
}

// ─── AVATAR ─────────────────────────────────────────────────
class BrutalAvatar extends StatelessWidget {
  final String? imageUrl;
  final String name;
  final double size;
  final Color? backgroundColor;

  const BrutalAvatar({
    super.key, this.imageUrl, required this.name,
    this.size = 40, this.backgroundColor,
  });

  String get initials => name.trim().split(' ').map((s) => s.isNotEmpty ? s[0] : '').take(2).join().toUpperCase();

  // Generate a color from name
  Color get _generatedColor {
    if (backgroundColor != null) return backgroundColor!;
    final colors = [
      AppColors.yellow, AppColors.purpleBg, AppColors.pinkBg,
      AppColors.tealBg, AppColors.orangeBg, AppColors.infoBg, AppColors.successBg,
    ];
    final idx = name.codeUnits.fold<int>(0, (a, b) => a + b) % colors.length;
    return colors[idx];
  }

  @override
  Widget build(BuildContext context) {
    return Container(
      width: size, height: size,
      decoration: BoxDecoration(
        color: _generatedColor,
        border: Border.all(color: AppColors.black, width: 2),
        boxShadow: const [BoxShadow(color: AppColors.black, offset: Offset(2, 2))],
      ),
      child: Center(
        child: Text(
          initials,
          style: TextStyle(
            fontFamily: 'SpaceGrotesk',
            fontWeight: FontWeight.w700,
            fontSize: size * 0.36,
            color: AppColors.black,
          ),
        ),
      ),
    );
  }
}

// ─── ACTION BUTTON (round, large) ───────────────────────────
class ActionButton extends StatefulWidget {
  final IconData icon;
  final String label;
  final Color color;
  final Color iconColor;
  final VoidCallback? onTap;
  final double size;

  const ActionButton({
    super.key,
    required this.icon,
    required this.label,
    required this.color,
    this.iconColor = AppColors.black,
    this.onTap,
    this.size = 56,
  });

  @override
  State<ActionButton> createState() => _ActionButtonState();
}

class _ActionButtonState extends State<ActionButton> {
  bool _pressed = false;

  @override
  Widget build(BuildContext context) {
    return Column(mainAxisSize: MainAxisSize.min, children: [
      GestureDetector(
        onTapDown: (_) { setState(() => _pressed = true); HapticFeedback.selectionClick(); },
        onTapUp: (_) => setState(() => _pressed = false),
        onTapCancel: () => setState(() => _pressed = false),
        onTap: widget.onTap,
        child: AnimatedContainer(
          duration: const Duration(milliseconds: 80),
          width: widget.size, height: widget.size,
          transform: Matrix4.translationValues(_pressed ? 2 : 0, _pressed ? 2 : 0, 0),
          decoration: BoxDecoration(
            color: widget.color,
            border: Border.all(color: AppColors.black, width: 2),
            boxShadow: [BoxShadow(color: AppColors.black, offset: Offset(_pressed ? 1 : 4, _pressed ? 1 : 4))],
          ),
          child: Icon(widget.icon, size: widget.size * 0.4, color: widget.iconColor),
        ),
      ),
      const SizedBox(height: 6),
      Text(widget.label, style: const TextStyle(fontFamily: 'SpaceGrotesk', fontWeight: FontWeight.w700, fontSize: 10, color: AppColors.dark)),
    ]);
  }
}
