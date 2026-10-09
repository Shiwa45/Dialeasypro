import 'package:flutter/material.dart';
import 'package:flutter/services.dart';

import '../../core/theme/colors.dart';

/// "Was the call answered?" — two buttons, used wherever a call outcome is
/// set (the post-call screen and the call outcome sheet).
///
/// They were ChoiceChips whose selected colour was a pale tint (Answered) or
/// the same light grey as an unselected chip (Not answered), so tapping one
/// barely changed it and looked as if nothing had happened. The chosen one is
/// now solid — green for answered, red for not — with white text and a tick,
/// and the other stays outlined.
class AnsweredToggle extends StatelessWidget {
  /// null until the agent chooses.
  final bool? value;
  final ValueChanged<bool> onChanged;

  const AnsweredToggle({super.key, required this.value, required this.onChanged});

  @override
  Widget build(BuildContext context) {
    return Row(children: [
      Expanded(child: _Option(
        label: 'Answered',
        icon: Icons.call_rounded,
        color: AppColors.success,
        selected: value == true,
        onTap: () => onChanged(true),
      )),
      const SizedBox(width: 10),
      Expanded(child: _Option(
        label: 'Not answered',
        icon: Icons.call_missed_rounded,
        color: AppColors.error,
        selected: value == false,
        onTap: () => onChanged(false),
      )),
    ]);
  }
}

class _Option extends StatelessWidget {
  final String label;
  final IconData icon;
  final Color color;
  final bool selected;
  final VoidCallback onTap;

  const _Option({
    required this.label,
    required this.icon,
    required this.color,
    required this.selected,
    required this.onTap,
  });

  @override
  Widget build(BuildContext context) {
    final fg = selected ? AppColors.white : color;
    return Semantics(
      button: true,
      selected: selected,
      label: label,
      child: Material(
        color: Colors.transparent,
        child: InkWell(
          borderRadius: BorderRadius.circular(12),
          onTap: () {
            HapticFeedback.selectionClick();
            onTap();
          },
          child: AnimatedContainer(
            duration: const Duration(milliseconds: 160),
            curve: Curves.easeOut,
            height: 48,
            padding: const EdgeInsets.symmetric(horizontal: 10),
            decoration: BoxDecoration(
              color: selected ? color : AppColors.white,
              borderRadius: BorderRadius.circular(12),
              border: Border.all(color: color, width: selected ? 2 : 1.4),
              boxShadow: selected
                  ? [BoxShadow(color: color.withValues(alpha: 0.35), blurRadius: 10, offset: const Offset(0, 4))]
                  : null,
            ),
            child: Row(mainAxisAlignment: MainAxisAlignment.center, children: [
              Icon(selected ? Icons.check_circle_rounded : icon, size: 18, color: fg),
              const SizedBox(width: 6),
              Flexible(
                child: Text(
                  label,
                  overflow: TextOverflow.ellipsis,
                  style: TextStyle(
                    fontFamily: 'PlusJakartaSans',
                    fontWeight: selected ? FontWeight.w800 : FontWeight.w600,
                    fontSize: 14,
                    color: fg,
                  ),
                ),
              ),
            ]),
          ),
        ),
      ),
    );
  }
}
