import 'dart:ui' show FontFeature;

import 'package:flutter/material.dart';

// ============================================================
// DialEasypro — Colour & design system (TeleCRM)
//
// Forest-green deep surfaces, cool-grey page, white cards, green actions and
// a blue second accent. Matches the web app's index.css token-for-token so
// the two products look like one.
//
// Every public name from the earlier palettes is KEPT and repointed at the
// new values. Screens reference `AppColors.yellow`, `.dark`, `.brutalShadow`
// and friends in hundreds of `const` widgets; renaming them would mean
// touching every file to gain nothing, and missing one shows up as an
// off-theme control.
// ============================================================

class AppColors {
  AppColors._();

  // ---- Surfaces — cool grey page, white cards ---------------
  static const Color paper     = Color(0xFFF3F6FA);
  static const Color surface   = Color(0xFFFFFFFF);
  static const Color surface2  = Color(0xFFF7F9FC);
  static const Color sunken    = Color(0xFFEEF2F6);
  static const Color line      = Color(0xFFE2E8F0);
  static const Color line2     = Color(0xFFCBD5E1);
  static const Color line3     = Color(0xFF94A3B8);

  // ---- Deep green (was ink) and text -----------------------
  // `ink` is the forest green of the web rail: every dark slab in the app
  // (dialer, snackbars, the login panel) now reads as the same deep green.
  static const Color ink       = Color(0xFF062A20);
  static const Color ink2      = Color(0xFF0C4634);
  static const Color text      = Color(0xFF0F1B2D);
  static const Color text2     = Color(0xFF475569);
  static const Color text3     = Color(0xFF64748B);

  // ---- Brand — green actions ---------------------------------
  static const Color brand     = Color(0xFF0F8A5F);
  static const Color brand600  = Color(0xFF0C7650);
  static const Color brand700  = Color(0xFF062A20);
  static const Color brand50   = Color(0xFFE4F6EE);
  static const Color brandInk  = Color(0xFF0A7A53);
  // Mint — the active-item pill and highlights on the deep green.
  static const Color mint      = Color(0xFF9FF3C9);
  static const Color mint2     = Color(0xFF6FE0A6);
  static const Color mintInk   = Color(0xFF053424);
  static const Color mintSoft  = Color(0xFF7DE8B3);

  // ---- Second accent — blue (was brass) ----------------------
  static const Color brass     = Color(0xFF1D64D8);
  static const Color brass600  = Color(0xFF1A56BB);
  static const Color brass50   = Color(0xFFE7EFFD);
  static const Color blue      = brass;
  static const Color blueBg    = brass50;

  // ---- Situational — each colour means one thing -----------
  static const Color hot       = Color(0xFFC81E1E);
  static const Color hotBg     = Color(0xFFFDE8E8);
  static const Color warm      = Color(0xFFC2560C);
  static const Color warmBg    = Color(0xFFFFF0E5);
  static const Color cold      = Color(0xFF3B6EA8);
  static const Color coldBg    = Color(0xFFE8EFF8);
  static const Color won       = Color(0xFF15803D);
  static const Color wonBg     = Color(0xFFDCF5E5);
  static const Color lost      = Color(0xFF64748B);
  static const Color lostBg    = Color(0xFFEEF2F6);
  static const Color visit     = Color(0xFF7A4FD6);
  static const Color visitBg   = Color(0xFFF1EBFD);
  static const Color amber     = Color(0xFFE0A800);
  static const Color amberBg   = Color(0xFFFFF6D6);
  static const Color amberInk  = Color(0xFF8A6500);

  // ---- Legacy names, repointed -----------------------------
  // Kept because hundreds of call sites use them. `yellow` points at the
  // BRAND GREEN: every place it is used (focus rings, the logo tile, section
  // icons, quick actions, the refresh spinner) is a primary position.
  static const Color yellow      = brand;
  static const Color yellowDark  = brand600;
  static const Color yellowBg    = brand50;
  static const Color dark        = ink;
  static const Color muted       = text2;
  static const Color background  = paper;
  static const Color cream       = brand50;

  // `black` is deliberately NOT pure black: the theme has no #000 anywhere.
  static const Color black     = text;
  static const Color white     = surface;
  static const Color grey      = text2;
  static const Color greyLight = line;
  static const Color greyDark  = text;

  // ---- Functional ------------------------------------------
  static const Color success    = won;
  static const Color successBg  = wonBg;
  static const Color error      = hot;
  static const Color errorBg    = hotBg;
  static const Color warning    = warm;
  static const Color warningBg  = warmBg;
  static const Color info       = brass;
  static const Color infoBg     = brass50;
  static const Color purple     = visit;
  static const Color purpleBg   = visitBg;
  static const Color pink       = hot;
  static const Color pinkBg     = hotBg;
  static const Color teal       = Color(0xFF15935F);
  static const Color tealBg     = Color(0xFFE3F6EC);
  static const Color orange     = warm;
  static const Color orangeBg   = warmBg;

  // ---- Lead status colour map ------------------------------
  // Same stage colours as the web pipeline donut.
  static const Map<String, _StatusColor> leadStatusColors = {
    'new':            _StatusColor(brand50,  brand,  brandInk),
    'attempted':      _StatusColor(brass50,  brass,  brass600),
    'contacted':      _StatusColor(amberBg,  amber,  amberInk),
    'interested':     _StatusColor(tealBg,   teal,   teal),
    'follow_up':      _StatusColor(warmBg,   warm,   Color(0xFFB24A09)),
    'negotiation':    _StatusColor(visitBg,  visit,  visit),
    'converted':      _StatusColor(wonBg,    won,    won),
    'lost':           _StatusColor(lostBg,   lost,   lost),
    'not_interested': _StatusColor(lostBg,   lost,   lost),
    'duplicate':      _StatusColor(sunken,   line3,  text2),
  };

  // ---- Priority colours ------------------------------------
  static const Map<String, Color> priorityColors = {
    'hot':  hot,
    'warm': warm,
    'cold': cold,
  };
  static const Map<String, Color> priorityBgColors = {
    'hot':  hotBg,
    'warm': warmBg,
    'cold': coldBg,
  };

  // ---- Gradients -------------------------------------------
  // `yellowGradient` is the primary call-to-action fill: brand green.
  static const LinearGradient yellowGradient = LinearGradient(
    colors: [Color(0xFF0C7650), brand],
    begin: Alignment.topLeft,
    end: Alignment.bottomRight,
  );

  // The deep forest green of the web rail.
  static const LinearGradient darkGradient = LinearGradient(
    colors: [ink2, ink],
    begin: Alignment.topLeft,
    end: Alignment.bottomRight,
  );

  static const LinearGradient successGradient = LinearGradient(
    colors: [won, Color(0xFF116632)],
    begin: Alignment.topLeft,
    end: Alignment.bottomRight,
  );

  // The mint pill on the active nav item.
  static const LinearGradient mintGradient = LinearGradient(
    colors: [mint, mint2],
  );

  // Soft green band behind the dashboard header.
  static const LinearGradient heroGradient = LinearGradient(
    colors: [paper, Color(0xFFE6F5ED)],
    begin: Alignment.topLeft,
    end: Alignment.bottomRight,
  );

  /// Tinted KPI card fill: the tone's pale tint fading into white.
  static LinearGradient tint(Color bg) => LinearGradient(
    colors: [bg, surface],
    stops: const [0, .72],
    begin: Alignment.topLeft,
    end: Alignment.bottomRight,
  );

  // ---- Elevation -------------------------------------------
  // Names kept from the neo-brutalist theme; nothing about them is "brutal".
  static const BoxShadow brutalShadow = BoxShadow(
    color: Color(0x1A0F1B2D), offset: Offset(0, 4), blurRadius: 14, spreadRadius: -6,
  );
  static const BoxShadow brutalShadowSm = BoxShadow(
    color: Color(0x0F0F1B2D), offset: Offset(0, 1), blurRadius: 2,
  );
  static const BoxShadow brutalShadowLg = BoxShadow(
    color: Color(0x4D0F1B2D), offset: Offset(0, 18), blurRadius: 40, spreadRadius: -18,
  );
  static const BoxShadow brutalShadowColor = BoxShadow(
    color: Color(0x660F8A5F), offset: Offset(0, 8), blurRadius: 18, spreadRadius: -10,
  );

  // ---- Borders ---------------------------------------------
  static Border get brutalBorder => Border.all(color: line, width: 1);
  static Border get brutalBorderThin => Border.all(color: line, width: 1);

  static const BorderRadius radius = BorderRadius.all(Radius.circular(14));
  static const BorderRadius radiusSm = BorderRadius.all(Radius.circular(8));
  static const BorderRadius radiusBtn = BorderRadius.all(Radius.circular(10));
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

  static const double borderWidth = 1.0;
  static const double inputHeight = 48.0;
  static const double buttonHeight = 48.0;
  static const double fabSize = 56.0;
}

// ============================================================
// Typography — Plus Jakarta Sans throughout, as on the web.
//
// One family, registered as static weights in pubspec.yaml, so plain
// `fontWeight` works everywhere. Numbers use tabular figures so columns line
// up; there is no separate monospace face any more.
// ============================================================

const String kFontFamily = 'PlusJakartaSans';

class AppTextStyles {
  AppTextStyles._();

  static const TextStyle display = TextStyle(
    fontFamily: kFontFamily, fontWeight: FontWeight.w800,
    fontSize: 28, letterSpacing: -0.7, color: AppColors.text, height: 1.12,
  );

  // Headings
  static const TextStyle h1 = TextStyle(
    fontFamily: kFontFamily, fontWeight: FontWeight.w800,
    fontSize: 26, letterSpacing: -0.6, color: AppColors.text, height: 1.15,
  );
  static const TextStyle h2 = TextStyle(
    fontFamily: kFontFamily, fontWeight: FontWeight.w800,
    fontSize: 20, letterSpacing: -0.4, color: AppColors.text, height: 1.2,
  );
  static const TextStyle h3 = TextStyle(
    fontFamily: kFontFamily, fontWeight: FontWeight.w700,
    fontSize: 16, letterSpacing: -0.2, color: AppColors.text, height: 1.25,
  );
  static const TextStyle h4 = TextStyle(
    fontFamily: kFontFamily, fontWeight: FontWeight.w700,
    fontSize: 14.5, letterSpacing: -0.1, color: AppColors.text, height: 1.3,
  );
  static const TextStyle h5 = TextStyle(
    fontFamily: kFontFamily, fontWeight: FontWeight.w700,
    fontSize: 13.5, color: AppColors.text, height: 1.3,
  );

  // Uppercase small label — field labels, KPI captions, section eyebrows.
  static const TextStyle label = TextStyle(
    fontFamily: kFontFamily, fontWeight: FontWeight.w700,
    fontSize: 10.5, letterSpacing: 0.8, color: AppColors.text2,
  );
  static const TextStyle button = TextStyle(
    fontFamily: kFontFamily, fontWeight: FontWeight.w700,
    fontSize: 14, letterSpacing: 0.1, color: AppColors.surface,
  );

  // Body
  static const TextStyle bodyLg = TextStyle(
    fontFamily: kFontFamily, fontWeight: FontWeight.w500,
    fontSize: 15, color: AppColors.text, height: 1.5,
  );
  static const TextStyle body = TextStyle(
    fontFamily: kFontFamily, fontWeight: FontWeight.w400,
    fontSize: 14, color: AppColors.text, height: 1.5,
  );
  static const TextStyle bodyMedium = TextStyle(
    fontFamily: kFontFamily, fontWeight: FontWeight.w500,
    fontSize: 14, color: AppColors.text, height: 1.45,
  );
  static const TextStyle bodyBold = TextStyle(
    fontFamily: kFontFamily, fontWeight: FontWeight.w700,
    fontSize: 14, color: AppColors.text, height: 1.45,
  );
  static const TextStyle caption = TextStyle(
    fontFamily: kFontFamily, fontWeight: FontWeight.w500,
    fontSize: 12, color: AppColors.text2, height: 1.4,
  );

  // Numbers — phone, ids, figures. Tabular so columns line up.
  static const TextStyle mono = TextStyle(
    fontFamily: kFontFamily, fontWeight: FontWeight.w600,
    fontSize: 12.5, color: AppColors.text2,
    fontFeatures: [FontFeature.tabularFigures()],
  );
  static const TextStyle monoLg = TextStyle(
    fontFamily: kFontFamily, fontWeight: FontWeight.w800,
    fontSize: 22, letterSpacing: -0.6, color: AppColors.text,
    fontFeatures: [FontFeature.tabularFigures()],
  );
}
