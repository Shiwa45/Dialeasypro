// CupertinoPageTransitionsBuilder is defined in cupertino, not material —
// material.dart does not re-export it.
import 'package:flutter/cupertino.dart';
import 'package:flutter/material.dart';
import 'package:flutter/services.dart';
import 'colors.dart';

// ============================================================
// DialEasypro — Material theme (TeleCRM)
//
// Matches the web app: cool-grey page, white cards with 14px corners, green
// primary actions, blue second accent, bold Plus Jakarta Sans headings.
// ============================================================

class AppTheme {
  AppTheme._();

  static const _radius = BorderRadius.all(Radius.circular(10));

  static ThemeData get theme => ThemeData(
    useMaterial3: true,
    colorScheme: const ColorScheme.light(
      primary: AppColors.brand,
      onPrimary: AppColors.surface,
      primaryContainer: AppColors.brand50,
      onPrimaryContainer: AppColors.brand700,
      secondary: AppColors.brass,
      onSecondary: AppColors.surface,
      tertiary: AppColors.visit,
      surfaceContainerLow: AppColors.surface2,
      surfaceContainer: AppColors.sunken,
      surface: AppColors.surface,
      onSurface: AppColors.text,
      surfaceContainerHighest: AppColors.surface2,
      outline: AppColors.line2,
      outlineVariant: AppColors.line,
      error: AppColors.hot,
      onError: AppColors.surface,
    ),
    scaffoldBackgroundColor: AppColors.paper,
    fontFamily: 'PlusJakartaSans',
    splashFactory: InkSparkle.splashFactory,

    appBarTheme: const AppBarTheme(
      backgroundColor: AppColors.surface,
      foregroundColor: AppColors.text,
      elevation: 0,
      scrolledUnderElevation: 0,
      centerTitle: false,
      titleSpacing: 16,
      titleTextStyle: TextStyle(
        fontFamily: 'PlusJakartaSans', fontWeight: FontWeight.w800,
        fontSize: 19, letterSpacing: -0.4, color: AppColors.text,
      ),
      systemOverlayStyle: SystemUiOverlayStyle(
        statusBarColor: Colors.transparent,
        statusBarIconBrightness: Brightness.dark,
      ),
      // A hairline, not a 2px slab.
      shape: Border(bottom: BorderSide(color: AppColors.line, width: 1)),
    ),

    cardTheme: const CardThemeData(
      color: AppColors.surface,
      elevation: 0,
      margin: EdgeInsets.zero,
      shape: RoundedRectangleBorder(
        borderRadius: BorderRadius.all(Radius.circular(14)),
        side: BorderSide(color: AppColors.line, width: 1),
      ),
    ),

    bottomNavigationBarTheme: const BottomNavigationBarThemeData(
      backgroundColor: AppColors.surface,
      selectedItemColor: AppColors.brand,
      unselectedItemColor: AppColors.text3,
      selectedLabelStyle: TextStyle(fontFamily: 'PlusJakartaSans', fontWeight: FontWeight.w700, fontSize: 11),
      unselectedLabelStyle: TextStyle(fontFamily: 'PlusJakartaSans', fontWeight: FontWeight.w500, fontSize: 11),
      elevation: 0,
      type: BottomNavigationBarType.fixed,
    ),

    inputDecorationTheme: InputDecorationTheme(
      filled: true,
      fillColor: AppColors.surface,
      contentPadding: const EdgeInsets.symmetric(horizontal: 14, vertical: 14),
      hintStyle: const TextStyle(color: AppColors.text3, fontSize: 14),
      labelStyle: const TextStyle(color: AppColors.text2, fontSize: 14),
      border: const OutlineInputBorder(
        borderRadius: _radius,
        borderSide: BorderSide(color: AppColors.line2, width: 1),
      ),
      enabledBorder: const OutlineInputBorder(
        borderRadius: _radius,
        borderSide: BorderSide(color: AppColors.line2, width: 1),
      ),
      focusedBorder: const OutlineInputBorder(
        borderRadius: _radius,
        borderSide: BorderSide(color: AppColors.brand, width: 1.6),
      ),
      errorBorder: const OutlineInputBorder(
        borderRadius: _radius,
        borderSide: BorderSide(color: AppColors.hot, width: 1),
      ),
    ),

    elevatedButtonTheme: ElevatedButtonThemeData(
      style: ElevatedButton.styleFrom(
        backgroundColor: AppColors.brand,
        foregroundColor: AppColors.surface,
        elevation: 0,
        padding: const EdgeInsets.symmetric(horizontal: 18, vertical: 14),
        shape: const RoundedRectangleBorder(borderRadius: _radius),
        textStyle: AppTextStyles.button,
      ),
    ),

    outlinedButtonTheme: OutlinedButtonThemeData(
      style: OutlinedButton.styleFrom(
        foregroundColor: AppColors.text,
        side: const BorderSide(color: AppColors.line2, width: 1),
        padding: const EdgeInsets.symmetric(horizontal: 16, vertical: 12),
        shape: const RoundedRectangleBorder(borderRadius: _radius),
      ),
    ),

    textButtonTheme: TextButtonThemeData(
      style: TextButton.styleFrom(
        foregroundColor: AppColors.brandInk,
        textStyle: const TextStyle(fontFamily: 'PlusJakartaSans', fontWeight: FontWeight.w700, fontSize: 13.5),
      ),
    ),

    floatingActionButtonTheme: const FloatingActionButtonThemeData(
      backgroundColor: AppColors.brand,
      foregroundColor: AppColors.surface,
      elevation: 3,
      shape: RoundedRectangleBorder(borderRadius: BorderRadius.all(Radius.circular(16))),
    ),

    chipTheme: const ChipThemeData(
      backgroundColor: AppColors.sunken,
      selectedColor: AppColors.brand50,
      labelStyle: TextStyle(fontFamily: 'PlusJakartaSans', fontSize: 12, fontWeight: FontWeight.w700, color: AppColors.text2),
      side: BorderSide.none,
      shape: RoundedRectangleBorder(borderRadius: BorderRadius.all(Radius.circular(999))),
      padding: EdgeInsets.symmetric(horizontal: 8, vertical: 2),
    ),

    dividerTheme: const DividerThemeData(color: AppColors.line, thickness: 1, space: 1),

    dialogTheme: const DialogThemeData(
      backgroundColor: AppColors.surface,
      elevation: 0,
      shape: RoundedRectangleBorder(
        borderRadius: BorderRadius.all(Radius.circular(20)),
        side: BorderSide(color: AppColors.line, width: 1),
      ),
      titleTextStyle: TextStyle(
        fontFamily: 'PlusJakartaSans', fontWeight: FontWeight.w800, fontSize: 18, color: AppColors.text,
      ),
    ),

    bottomSheetTheme: const BottomSheetThemeData(
      backgroundColor: AppColors.surface,
      elevation: 0,
      shape: RoundedRectangleBorder(
        borderRadius: BorderRadius.vertical(top: Radius.circular(22)),
      ),
    ),

    snackBarTheme: const SnackBarThemeData(
      backgroundColor: AppColors.ink,
      contentTextStyle: TextStyle(fontFamily: 'PlusJakartaSans', color: AppColors.surface, fontSize: 13),
      shape: RoundedRectangleBorder(borderRadius: BorderRadius.all(Radius.circular(12))),
      behavior: SnackBarBehavior.floating,
    ),

    tabBarTheme: const TabBarThemeData(
      labelColor: AppColors.brandInk,
      unselectedLabelColor: AppColors.text2,
      indicatorColor: AppColors.brand,
      indicatorSize: TabBarIndicatorSize.tab,
      dividerColor: AppColors.line,
      labelStyle: TextStyle(fontFamily: 'PlusJakartaSans', fontWeight: FontWeight.w700, fontSize: 13.5),
      unselectedLabelStyle: TextStyle(fontFamily: 'PlusJakartaSans', fontWeight: FontWeight.w600, fontSize: 13.5),
    ),

    progressIndicatorTheme: const ProgressIndicatorThemeData(
      color: AppColors.brand,
      linearTrackColor: AppColors.sunken,
      circularTrackColor: AppColors.sunken,
    ),

    switchTheme: SwitchThemeData(
      thumbColor: WidgetStateProperty.resolveWith(
        (s) => s.contains(WidgetState.selected) ? AppColors.surface : AppColors.surface,
      ),
      trackColor: WidgetStateProperty.resolveWith(
        (s) => s.contains(WidgetState.selected) ? AppColors.brand : AppColors.line2,
      ),
    ),

    checkboxTheme: CheckboxThemeData(
      fillColor: WidgetStateProperty.resolveWith(
        (s) => s.contains(WidgetState.selected) ? AppColors.brand : Colors.transparent,
      ),
      side: const BorderSide(color: AppColors.line2, width: 1.4),
      shape: const RoundedRectangleBorder(borderRadius: BorderRadius.all(Radius.circular(4))),
    ),

    radioTheme: RadioThemeData(
      fillColor: WidgetStateProperty.resolveWith(
        (s) => s.contains(WidgetState.selected) ? AppColors.brand : AppColors.line2,
      ),
    ),

    pageTransitionsTheme: const PageTransitionsTheme(builders: {
      TargetPlatform.android: CupertinoPageTransitionsBuilder(),
      TargetPlatform.iOS: CupertinoPageTransitionsBuilder(),
    }),
  );
}
