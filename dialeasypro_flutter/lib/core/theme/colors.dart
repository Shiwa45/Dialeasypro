import 'package:flutter/material.dart';

// ============================================================
// DialEasypro — Color & Design System
// Neobrutalist but COLORFUL — more visual hierarchy
// ============================================================

class AppColors {
  AppColors._();

  // ---- Brand Identity --------------------------------------
  static const Color yellow      = Color(0xFFFFE17C);
  static const Color yellowDark  = Color(0xFFFFCD2C);
  static const Color dark        = Color(0xFF171E19);
  static const Color muted       = Color(0xFFB7C6C2);
  static const Color background  = Color(0xFFF5F4F0);
  static const Color cream       = Color(0xFFFFFBEE);

  // ---- Base ------------------------------------------------
  static const Color black     = Color(0xFF000000);
  static const Color white     = Color(0xFFFFFFFF);
  static const Color grey      = Color(0xFF6B7280);
  static const Color greyLight = Color(0xFFE5E7EB);
  static const Color greyDark  = Color(0xFF374151);

  // ---- Functional Colors -----------------------------------
  static const Color success    = Color(0xFF22C55E);
  static const Color successBg  = Color(0xFFDCFCE7);
  static const Color error      = Color(0xFFEF4444);
  static const Color errorBg    = Color(0xFFFEE2E2);
  static const Color warning    = Color(0xFFF59E0B);
  static const Color warningBg  = Color(0xFFFEF3C7);
  static const Color info       = Color(0xFF3B82F6);
  static const Color infoBg     = Color(0xFFDBEAFE);
  static const Color purple     = Color(0xFF8B5CF6);
  static const Color purpleBg   = Color(0xFFEDE9FE);
  static const Color pink       = Color(0xFFEC4899);
  static const Color pinkBg     = Color(0xFFFCE7F3);
  static const Color teal       = Color(0xFF14B8A6);
  static const Color tealBg     = Color(0xFFCCFBF1);
  static const Color orange     = Color(0xFFF97316);
  static const Color orangeBg   = Color(0xFFFFEDD5);

  // ---- Lead Status Color Map -------------------------------
  static const Map<String, _StatusColor> leadStatusColors = {
    'new':            _StatusColor(infoBg,    info,      Color(0xFF0369A1)),
    'attempted':      _StatusColor(orangeBg,  orange,    Color(0xFFC2410C)),
    'contacted':      _StatusColor(infoBg,    info,      Color(0xFF1E40AF)),
    'interested':     _StatusColor(successBg, success,   Color(0xFF15803D)),
    'follow_up':      _StatusColor(yellowBg,  warning,   Color(0xFF854D0E)),
    'negotiation':    _StatusColor(purpleBg,  purple,    Color(0xFF6D28D9)),
    'converted':      _StatusColor(Color(0xFFD1FAE5), Color(0xFF10B981), Color(0xFF065F46)),
    'lost':           _StatusColor(errorBg,   error,     Color(0xFF991B1B)),
    'not_interested': _StatusColor(errorBg,   error,     Color(0xFF991B1B)),
    'duplicate':      _StatusColor(Color(0xFFF3F4F6), Color(0xFF9CA3AF), greyDark),
  };

  static const Color yellowBg = Color(0xFFFEF9C3);

  // ---- Priority Colors -------------------------------------
  // Keys are the backend's LeadPriority values (hot/warm/cold). A colour for
  // a priority the API cannot store would only ever render for data that
  // failed to save.
  static const Map<String, Color> priorityColors = {
    'hot':  error,
    'warm': yellow,
    'cold': grey,
  };

  // ---- Gradients (used sparingly for emphasis) -------------
  static const LinearGradient yellowGradient = LinearGradient(
    colors: [yellow, yellowDark],
    begin: Alignment.topLeft,
    end: Alignment.bottomRight,
  );

  static const LinearGradient darkGradient = LinearGradient(
    colors: [dark, Color(0xFF0A0F0B)],
    begin: Alignment.topLeft,
    end: Alignment.bottomRight,
  );

  static const LinearGradient successGradient = LinearGradient(
    colors: [Color(0xFF22C55E), Color(0xFF16A34A)],
    begin: Alignment.topLeft,
    end: Alignment.bottomRight,
  );

  // ---- Shadows ---------------------------------------------
  static const BoxShadow brutalShadow = BoxShadow(
    color: black, offset: Offset(4, 4), blurRadius: 0,
  );
  static const BoxShadow brutalShadowSm = BoxShadow(
    color: black, offset: Offset(3, 3), blurRadius: 0,
  );
  static const BoxShadow brutalShadowLg = BoxShadow(
    color: black, offset: Offset(6, 6), blurRadius: 0,
  );
  static const BoxShadow brutalShadowColor = BoxShadow(
    color: yellow, offset: Offset(4, 4), blurRadius: 0,
  );

  // ---- Border ----------------------------------------------
  static Border get brutalBorder => Border.all(color: black, width: 2);
  static Border get brutalBorderThin => Border.all(color: black, width: 1.5);
}

class _StatusColor {
  final Color background;
  final Color border;
  final Color text;
  const _StatusColor(this.background, this.border, this.text);
}

// ============================================================
// Dimensions & Spacing
// ============================================================

class AppDimens {
  AppDimens._();

  static const double s4  = 4.0;
  static const double s6  = 6.0;
  static const double s8  = 8.0;
  static const double s10 = 10.0;
  static const double s12 = 12.0;
  static const double s14 = 14.0;
  static const double s16 = 16.0;
  static const double s20 = 20.0;
  static const double s24 = 24.0;
  static const double s32 = 32.0;
  static const double s40 = 40.0;
  static const double s48 = 48.0;
  static const double s64 = 64.0;

  static const double borderWidth = 2.0;
  static const double inputHeight = 50.0;
  static const double buttonHeight = 50.0;
  static const double fabSize = 60.0;
}

// ============================================================
// Typography
// ============================================================

class AppTextStyles {
  AppTextStyles._();

  // Display & Heading (Space Grotesk)
  static const TextStyle h1 = TextStyle(
    fontFamily: 'SpaceGrotesk', fontWeight: FontWeight.w700, fontSize: 28, letterSpacing: -0.5, color: AppColors.black, height: 1.1,
  );
  static const TextStyle h2 = TextStyle(
    fontFamily: 'SpaceGrotesk', fontWeight: FontWeight.w700, fontSize: 22, letterSpacing: -0.3, color: AppColors.black, height: 1.15,
  );
  static const TextStyle h3 = TextStyle(
    fontFamily: 'SpaceGrotesk', fontWeight: FontWeight.w700, fontSize: 18, color: AppColors.black, height: 1.2,
  );
  static const TextStyle h4 = TextStyle(
    fontFamily: 'SpaceGrotesk', fontWeight: FontWeight.w700, fontSize: 15, color: AppColors.black, height: 1.25,
  );
  static const TextStyle h5 = TextStyle(
    fontFamily: 'SpaceGrotesk', fontWeight: FontWeight.w600, fontSize: 13, color: AppColors.black, height: 1.3,
  );
  static const TextStyle label = TextStyle(
    fontFamily: 'SpaceGrotesk', fontWeight: FontWeight.w700, fontSize: 10, letterSpacing: 0.8, color: AppColors.greyDark,
  );
  static const TextStyle button = TextStyle(
    fontFamily: 'SpaceGrotesk', fontWeight: FontWeight.w700, fontSize: 14, letterSpacing: 0.3, color: AppColors.white,
  );

  // Body (DM Sans)
  static const TextStyle bodyLg = TextStyle(
    fontFamily: 'DMSans', fontWeight: FontWeight.w400, fontSize: 15, color: AppColors.black, height: 1.5,
  );
  static const TextStyle body = TextStyle(
    fontFamily: 'DMSans', fontWeight: FontWeight.w400, fontSize: 13, color: AppColors.black, height: 1.5,
  );
  static const TextStyle bodyMedium = TextStyle(
    fontFamily: 'DMSans', fontWeight: FontWeight.w500, fontSize: 13, color: AppColors.black, height: 1.4,
  );
  static const TextStyle bodyBold = TextStyle(
    fontFamily: 'DMSans', fontWeight: FontWeight.w600, fontSize: 13, color: AppColors.black, height: 1.4,
  );
  static const TextStyle caption = TextStyle(
    fontFamily: 'DMSans', fontWeight: FontWeight.w400, fontSize: 11, color: AppColors.grey, height: 1.4,
  );

  // Mono (numbers, phone, IDs)
  static const TextStyle mono = TextStyle(
    fontFamily: 'monospace', fontWeight: FontWeight.w500, fontSize: 12, letterSpacing: 0.2, color: AppColors.greyDark,
  );
  static const TextStyle monoLg = TextStyle(
    fontFamily: 'monospace', fontWeight: FontWeight.w700, fontSize: 18, letterSpacing: 0.4, color: AppColors.black,
  );
}
