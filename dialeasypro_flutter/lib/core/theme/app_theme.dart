// CupertinoPageTransitionsBuilder is defined in cupertino, not material —
// material.dart does not re-export it.
import 'package:flutter/cupertino.dart';
import 'package:flutter/material.dart';
import 'package:flutter/services.dart';
import 'colors.dart';

// ============================================================
// DialEasypro — Material theme (BrokerStack)
//
// Square corners and 2px black rules are replaced by hairlines and small
// radii. The primary colour is the brand green: it was the old brand yellow,
// which Material also used for focus rings, selection handles and progress
// indicators — all of which read as "warning" against the new palette.
// ============================================================

class AppTheme {
  AppTheme._();

  static const _radius = BorderRadius.all(Radius.circular(8));

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
      surface: AppColors.surface,
      onSurface: AppColors.text,
      surfaceContainerHighest: AppColors.surface2,
      outline: AppColors.line2,
      outlineVariant: AppColors.line,
      error: AppColors.hot,
      onError: AppColors.surface,
    ),
    scaffoldBackgroundColor: AppColors.paper,
    fontFamily: 'Archivo',
    splashFactory: InkSparkle.splashFactory,

    appBarTheme: const AppBarTheme(
      backgroundColor: AppColors.paper,
      foregroundColor: AppColors.text,
      elevation: 0,
      scrolledUnderElevation: 0,
      centerTitle: false,
      titleSpacing: 16,
      titleTextStyle: TextStyle(
        fontFamily: 'Fraunces', fontWeight: FontWeight.w600,
        fontSize: 19, letterSpacing: -0.3, color: AppColors.text,
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
        borderRadius: BorderRadius.all(Radius.circular(10)),
        side: BorderSide(color: AppColors.line, width: 1),
      ),
    ),

    bottomNavigationBarTheme: const BottomNavigationBarThemeData(
      backgroundColor: AppColors.surface,
      selectedItemColor: AppColors.brand,
      unselectedItemColor: AppColors.text3,
      selectedLabelStyle: TextStyle(fontFamily: 'Archivo', fontWeight: FontWeight.w600, fontSize: 10.5),
      unselectedLabelStyle: TextStyle(fontFamily: 'Archivo', fontWeight: FontWeight.w500, fontSize: 10.5),
      elevation: 0,
      type: BottomNavigationBarType.fixed,
    ),

    inputDecorationTheme: InputDecorationTheme(
      filled: true,
      fillColor: AppColors.surface,
      contentPadding: const EdgeInsets.symmetric(horizontal: 12, vertical: 12),
      hintStyle: const TextStyle(color: AppColors.text3, fontSize: 13.5),
      labelStyle: const TextStyle(color: AppColors.text2, fontSize: 13.5),
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
        padding: const EdgeInsets.symmetric(horizontal: 16, vertical: 12),
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
      style: TextButton.styleFrom(foregroundColor: AppColors.brand),
    ),

    floatingActionButtonTheme: const FloatingActionButtonThemeData(
      backgroundColor: AppColors.brand,
      foregroundColor: AppColors.surface,
      elevation: 2,
      shape: RoundedRectangleBorder(borderRadius: BorderRadius.all(Radius.circular(14))),
    ),

    chipTheme: const ChipThemeData(
      backgroundColor: Color(0xFFEDF0EA),
      labelStyle: TextStyle(fontFamily: 'Archivo', fontSize: 11.5, fontWeight: FontWeight.w600, color: AppColors.text2),
      side: BorderSide.none,
      shape: RoundedRectangleBorder(borderRadius: BorderRadius.all(Radius.circular(5))),
      padding: EdgeInsets.symmetric(horizontal: 8, vertical: 2),
    ),

    dividerTheme: const DividerThemeData(color: AppColors.line, thickness: 1, space: 1),

    dialogTheme: const DialogThemeData(
      backgroundColor: AppColors.surface,
      elevation: 0,
      shape: RoundedRectangleBorder(
        borderRadius: BorderRadius.all(Radius.circular(12)),
        side: BorderSide(color: AppColors.line, width: 1),
      ),
      titleTextStyle: TextStyle(
        fontFamily: 'Fraunces', fontWeight: FontWeight.w600, fontSize: 18, color: AppColors.text,
      ),
    ),

    bottomSheetTheme: const BottomSheetThemeData(
      backgroundColor: AppColors.surface,
      elevation: 0,
      shape: RoundedRectangleBorder(
        borderRadius: BorderRadius.vertical(top: Radius.circular(14)),
      ),
    ),

    snackBarTheme: const SnackBarThemeData(
      backgroundColor: AppColors.ink,
      contentTextStyle: TextStyle(fontFamily: 'Archivo', color: AppColors.surface, fontSize: 13),
      shape: RoundedRectangleBorder(borderRadius: BorderRadius.all(Radius.circular(10))),
      behavior: SnackBarBehavior.floating,
    ),

    tabBarTheme: const TabBarThemeData(
      labelColor: AppColors.brand,
      unselectedLabelColor: AppColors.text2,
      indicatorColor: AppColors.brand,
      indicatorSize: TabBarIndicatorSize.tab,
      dividerColor: AppColors.line,
      labelStyle: TextStyle(fontFamily: 'Archivo', fontWeight: FontWeight.w600, fontSize: 13),
      unselectedLabelStyle: TextStyle(fontFamily: 'Archivo', fontWeight: FontWeight.w500, fontSize: 13),
    ),

    progressIndicatorTheme: const ProgressIndicatorThemeData(
      color: AppColors.brand,
      linearTrackColor: Color(0xFFE7EBE4),
      circularTrackColor: Color(0xFFE7EBE4),
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
