import 'dart:ui' show FontFeature, FontVariation;

import 'package:flutter/material.dart';

// ============================================================
// DialEasypro — Colour & design system (BrokerStack)
//
// Drafting-paper surfaces, survey-ink text, brand green and brass. Matches the
// web app's index.css token-for-token so the two products look like one.
//
// Every public name from the previous neo-brutalist palette is KEPT and
// repointed at the new values. Screens across the app reference `AppColors.
// yellow`, `.dark`, `.brutalShadow` and friends in hundreds of places;
// renaming them would mean touching every file to gain nothing, and missing
// one shows up as an off-theme control. Names that no longer describe their
// colour (`yellow` is now brass) are marked deprecated so new code reaches for
// the right one.
// ============================================================

class AppColors {
  AppColors._();

  // ---- Surfaces — drafting paper, not white-on-white -------
  static const Color paper     = Color(0xFFF1F4EF);
  static const Color surface   = Color(0xFFFFFFFF);
  static const Color surface2  = Color(0xFFFAFBF8);
  static const Color line      = Color(0xFFE0E5DC);
  static const Color line2     = Color(0xFFC9D0C4);
  static const Color line3     = Color(0xFFAEB8A9);

  // ---- Ink — near-black with a green cast ------------------
  static const Color ink       = Color(0xFF111A16);
  static const Color text      = Color(0xFF16211C);
  static const Color text2     = Color(0xFF5C6A62);
  static const Color text3     = Color(0xFF8B968F);

  // ---- Brand -----------------------------------------------
  static const Color brand     = Color(0xFF0B5F55);
  static const Color brand600  = Color(0xFF0A6E62);
  static const Color brand700  = Color(0xFF084A43);
  static const Color brand50   = Color(0xFFDDEBE8);
  static const Color brass     = Color(0xFFA97C1E);
  static const Color brass600  = Color(0xFFC0912A);
  static const Color brass50   = Color(0xFFF6ECD6);

  // ---- Situational — each colour means one thing -----------
  static const Color hot       = Color(0xFFCE3A22);
  static const Color hotBg     = Color(0xFFFAE3DD);
  static const Color warm      = Color(0xFFCF8A06);
  static const Color warmBg    = Color(0xFFF9EDD3);
  static const Color cold      = Color(0xFF5B7280);
  static const Color coldBg    = Color(0xFFE5EAED);
  static const Color won       = Color(0xFF1B7F4A);
  static const Color wonBg     = Color(0xFFDCEFE3);
  static const Color lost      = Color(0xFF89302E);
  static const Color lostBg    = Color(0xFFF2E0DF);
  static const Color visit     = Color(0xFF6244B8);
  static const Color visitBg   = Color(0xFFE7E1F7);

  // ---- Legacy names, repointed -----------------------------
  // These are the old neo-brutalist names, kept because 418 call sites across
  // the app use them, and repointed at the new palette. They are NOT marked
  // @Deprecated on purpose: that would emit 418 analyzer warnings and bury
  // anything real. Prefer the semantic names above in new code — `dark` is
  // ink, and `black` is not black.
  //
  // `yellow` points at the BRAND GREEN, not at brass.
  //
  // It was aimed at brass first, on the reasoning that gold is the nearest
  // thing to the old yellow. That was the wrong question. Every place this
  // name is used — focus rings, the logo tile, section-header icons, quick
  // action tiles, the pull-to-refresh spinner, the default snackbar — is a
  // PRIMARY position, and in the web theme every one of those is brand green.
  // Aiming them at brass turned the login screen into a sheet of gold and
  // left the app looking like the yellow theme it was supposed to replace.
  //
  // Brass survives as a sparing accent, and anything that genuinely wants it
  // now names `brass` directly.
  static const Color yellow      = brand;
  static const Color yellowDark  = brand600;
  static const Color yellowBg    = brand50;
  static const Color dark        = ink;
  static const Color muted       = text2;
  static const Color background  = paper;
  static const Color cream       = brass50;

  // `black` is deliberately NOT pure black: the theme has no #000 anywhere,
  // and text set in it against paper looks harsher than everything around it.
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
  static const Color info       = brand;
  static const Color infoBg     = brand50;
  static const Color purple     = visit;
  static const Color purpleBg   = visitBg;
  static const Color pink       = lost;
  static const Color pinkBg     = lostBg;
  static const Color teal       = brand600;
  static const Color tealBg     = brand50;
  static const Color orange     = brass;
  static const Color orangeBg   = brass50;

  // ---- Lead status colour map ------------------------------
  // One meaning per colour: everything still in play is brand/visit, anything
  // won is green, anything dead is the lost red.
  static const Map<String, _StatusColor> leadStatusColors = {
    'new':            _StatusColor(brand50,  brand,  brand),
    'attempted':      _StatusColor(coldBg,   cold,   cold),
    'contacted':      _StatusColor(visitBg,  visit,  visit),
    'interested':     _StatusColor(wonBg,    won,    won),
    'follow_up':      _StatusColor(warmBg,   warm,   Color(0xFF96650B)),
    'negotiation':    _StatusColor(brass50,  brass,  Color(0xFF87630F)),
    'converted':      _StatusColor(wonBg,    won,    brand700),
    'lost':           _StatusColor(lostBg,   lost,   lost),
    'not_interested': _StatusColor(lostBg,   lost,   lost),
    'duplicate':      _StatusColor(Color(0xFFEDF0EA), line3, text2),
  };

  // ---- Priority colours ------------------------------------
  // Keys are the backend's LeadPriority values (hot/warm/cold). A colour for
  // a priority the API cannot store would only ever render for data that
  // failed to save.
  static const Map<String, Color> priorityColors = {
    'hot':  hot,
    'warm': warm,
    'cold': cold,
  };

  // ---- Gradients -------------------------------------------
  static const LinearGradient yellowGradient = LinearGradient(
    colors: [brand600, brand],
    begin: Alignment.topLeft,
    end: Alignment.bottomRight,
  );

  static const LinearGradient darkGradient = LinearGradient(
    colors: [brand700, ink],
    begin: Alignment.topLeft,
    end: Alignment.bottomRight,
  );

  static const LinearGradient successGradient = LinearGradient(
    colors: [won, Color(0xFF166B3E)],
    begin: Alignment.topLeft,
    end: Alignment.bottomRight,
  );

  // ---- Elevation -------------------------------------------
  // Soft shadows replace the hard offset blocks. The names are kept because
  // they are referenced throughout the screens; nothing about them is
  // "brutal" any more.
  static const BoxShadow brutalShadow = BoxShadow(
    color: Color(0x1F111A16), offset: Offset(0, 8), blurRadius: 24, spreadRadius: -12,
  );
  static const BoxShadow brutalShadowSm = BoxShadow(
    color: Color(0x14111A16), offset: Offset(0, 1), blurRadius: 3,
  );
  static const BoxShadow brutalShadowLg = BoxShadow(
    color: Color(0x33111A16), offset: Offset(0, 14), blurRadius: 30, spreadRadius: -16,
  );
  static const BoxShadow brutalShadowColor = BoxShadow(
    color: Color(0x260B5F55), offset: Offset(0, 8), blurRadius: 20, spreadRadius: -10,
  );

  // ---- Borders ---------------------------------------------
  static Border get brutalBorder => Border.all(color: line, width: 1);
  static Border get brutalBorderThin => Border.all(color: line, width: 1);

  static const BorderRadius radius = BorderRadius.all(Radius.circular(10));
  static const BorderRadius radiusSm = BorderRadius.all(Radius.circular(6));
  static const BorderRadius radiusBtn = BorderRadius.all(Radius.circular(8));
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
  static const double buttonHeight = 46.0;
  static const double fabSize = 56.0;
}

// ============================================================
// Typography
//
// Archivo is registered as four static weights, so plain `fontWeight` works.
// Fraunces exists only as a variable font, so the two display styles pin their
// weight with `fontVariations` as well. FontVariation is const-constructible,
// which matters: these styles are used inside `const` widgets throughout the
// app and must stay const.
// ============================================================

const String _sans = 'Archivo';
const String _disp = 'Fraunces';
const String _mono = 'IBMPlexMono';

const List<FontVariation> _w600 = [FontVariation('wght', 600)];

class AppTextStyles {
  AppTextStyles._();

  // Display — the serif, reserved for real page titles.
  static const TextStyle display = TextStyle(
    fontFamily: _disp, fontVariations: _w600, fontWeight: FontWeight.w600,
    fontSize: 27, letterSpacing: -0.5, color: AppColors.text, height: 1.1,
  );

  // Headings
  static const TextStyle h1 = TextStyle(
    fontFamily: _disp, fontVariations: _w600, fontWeight: FontWeight.w600,
    fontSize: 27, letterSpacing: -0.5, color: AppColors.text, height: 1.12,
  );
  static const TextStyle h2 = TextStyle(
    fontFamily: _sans, fontWeight: FontWeight.w600,
    fontSize: 20, letterSpacing: -0.3, color: AppColors.text, height: 1.2,
  );
  static const TextStyle h3 = TextStyle(
    fontFamily: _sans, fontWeight: FontWeight.w600,
    fontSize: 16, letterSpacing: -0.2, color: AppColors.text, height: 1.25,
  );
  static const TextStyle h4 = TextStyle(
    fontFamily: _sans, fontWeight: FontWeight.w600,
    fontSize: 14, letterSpacing: -0.15, color: AppColors.text, height: 1.3,
  );
  static const TextStyle h5 = TextStyle(
    fontFamily: _sans, fontWeight: FontWeight.w600,
    fontSize: 13, color: AppColors.text, height: 1.3,
  );

  // Mono uppercase field label — the theme's signature small caps.
  static const TextStyle label = TextStyle(
    fontFamily: _mono, fontWeight: FontWeight.w500,
    fontSize: 9.5, letterSpacing: 1.3, color: AppColors.text3,
  );
  static const TextStyle button = TextStyle(
    fontFamily: _sans, fontWeight: FontWeight.w600,
    fontSize: 13.5, letterSpacing: 0.1, color: AppColors.surface,
  );

  // Body
  static const TextStyle bodyLg = TextStyle(
    fontFamily: _sans, fontWeight: FontWeight.w400,
    fontSize: 15, color: AppColors.text, height: 1.5,
  );
  static const TextStyle body = TextStyle(
    fontFamily: _sans, fontWeight: FontWeight.w400,
    fontSize: 13.5, color: AppColors.text, height: 1.5,
  );
  static const TextStyle bodyMedium = TextStyle(
    fontFamily: _sans, fontWeight: FontWeight.w500,
    fontSize: 13.5, color: AppColors.text, height: 1.45,
  );
  static const TextStyle bodyBold = TextStyle(
    fontFamily: _sans, fontWeight: FontWeight.w600,
    fontSize: 13.5, color: AppColors.text, height: 1.45,
  );
  static const TextStyle caption = TextStyle(
    fontFamily: _sans, fontWeight: FontWeight.w400,
    fontSize: 11.5, color: AppColors.text2, height: 1.4,
  );

  // Mono — numbers, phone, ids. Tabular so columns line up.
  static const TextStyle mono = TextStyle(
    fontFamily: _mono, fontWeight: FontWeight.w500,
    fontSize: 12, letterSpacing: 0.1, color: AppColors.text2,
    fontFeatures: [FontFeature.tabularFigures()],
  );
  static const TextStyle monoLg = TextStyle(
    fontFamily: _mono, fontWeight: FontWeight.w600,
    fontSize: 20, letterSpacing: -0.6, color: AppColors.text,
    fontFeatures: [FontFeature.tabularFigures()],
  );
}
