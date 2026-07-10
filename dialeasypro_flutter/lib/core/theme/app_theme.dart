import 'package:flutter/material.dart';
import 'package:flutter/services.dart';
import 'colors.dart';

class AppTheme {
  AppTheme._();

  static ThemeData get theme => ThemeData(
    useMaterial3: true,
    colorScheme: const ColorScheme.light(
      primary: AppColors.yellow,
      onPrimary: AppColors.black,
      secondary: AppColors.dark,
      onSecondary: AppColors.white,
      tertiary: AppColors.purple,
      surface: AppColors.white,
      onSurface: AppColors.black,
      error: AppColors.error,
      onError: AppColors.white,
      background: AppColors.background,
      onBackground: AppColors.black,
    ),
    scaffoldBackgroundColor: AppColors.background,
    fontFamily: 'DMSans',

    appBarTheme: const AppBarTheme(
      backgroundColor: AppColors.white,
      foregroundColor: AppColors.black,
      elevation: 0,
      scrolledUnderElevation: 0,
      centerTitle: false,
      titleSpacing: 16,
      titleTextStyle: TextStyle(
        fontFamily: 'SpaceGrotesk', fontWeight: FontWeight.w700, fontSize: 18, color: AppColors.black,
      ),
      systemOverlayStyle: SystemUiOverlayStyle(
        statusBarColor: Colors.transparent,
        statusBarIconBrightness: Brightness.dark,
      ),
      shape: Border(bottom: BorderSide(color: AppColors.black, width: 2)),
    ),

    bottomNavigationBarTheme: const BottomNavigationBarThemeData(
      backgroundColor: AppColors.white,
      selectedItemColor: AppColors.black,
      unselectedItemColor: AppColors.grey,
      selectedLabelStyle: TextStyle(fontFamily: 'SpaceGrotesk', fontWeight: FontWeight.w700, fontSize: 10),
      unselectedLabelStyle: TextStyle(fontFamily: 'DMSans', fontSize: 10),
      elevation: 0,
      type: BottomNavigationBarType.fixed,
    ),

    dialogTheme: const DialogThemeData(
      backgroundColor: AppColors.white,
      shape: RoundedRectangleBorder(
        borderRadius: BorderRadius.zero,
        side: BorderSide(color: AppColors.black, width: 2),
      ),
    ),

    bottomSheetTheme: const BottomSheetThemeData(
      backgroundColor: AppColors.white,
      shape: RoundedRectangleBorder(
        borderRadius: BorderRadius.vertical(top: Radius.circular(0)),
        side: BorderSide(color: AppColors.black, width: 2),
      ),
    ),

    snackBarTheme: const SnackBarThemeData(
      backgroundColor: AppColors.dark,
      contentTextStyle: TextStyle(fontFamily: 'DMSans', color: AppColors.white, fontSize: 13),
      shape: RoundedRectangleBorder(borderRadius: BorderRadius.zero),
      behavior: SnackBarBehavior.floating,
    ),

    tabBarTheme: const TabBarThemeData(
      labelColor: AppColors.black,
      unselectedLabelColor: AppColors.grey,
      indicatorColor: AppColors.yellow,
      indicatorSize: TabBarIndicatorSize.tab,
      labelStyle: TextStyle(fontFamily: 'SpaceGrotesk', fontWeight: FontWeight.w700, fontSize: 13),
      unselectedLabelStyle: TextStyle(fontFamily: 'DMSans', fontSize: 13),
    ),

    pageTransitionsTheme: const PageTransitionsTheme(builders: {
      TargetPlatform.android: CupertinoPageTransitionsBuilder(),
      TargetPlatform.iOS: CupertinoPageTransitionsBuilder(),
    }),
  );
}
