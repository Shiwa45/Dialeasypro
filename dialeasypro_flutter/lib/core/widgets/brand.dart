import 'package:flutter/material.dart';
import 'package:flutter_svg/flutter_svg.dart';

import '../theme/colors.dart';

// ============================================================
// Brand pieces shared with the web app: the DialEasy mark, the wordmark and
// the dashboard illustration. All three are PLACEHOLDER artwork drawn to
// match the design — swap the SVG strings for the real files when they exist.
// ============================================================

/// Handset with signal arcs. [onDark] draws the arcs white for the deep green
/// surfaces; otherwise they are ink so the mark reads on white.
class BrandMark extends StatelessWidget {
  final double size;
  final bool onDark;
  const BrandMark({super.key, this.size = 40, this.onDark = false});

  @override
  Widget build(BuildContext context) {
    final arc = onDark ? '#ffffff' : '#062a20';
    final hand = onDark ? '#7de8b3' : '#0f8a5f';
    return SvgPicture.string(
      '<svg viewBox="0 0 44 44" xmlns="http://www.w3.org/2000/svg">'
      '<path d="M9 12c0-1.7 1.3-3 3-3h5l2.6 6.5-3.2 2a13 13 0 0 0 6.1 6.1l2-3.2L31 23v5c0 1.7-1.3 3-3 3h-1C16.5 31 9 23.5 9 13z" fill="$hand"/>'
      '<path d="M25 8a11 11 0 0 1 11 11M25 13.5a5.5 5.5 0 0 1 5.5 5.5" fill="none" stroke="$arc" stroke-width="2.6" stroke-linecap="round"/>'
      '<path d="M7 30c4 7 13 10 21 7" fill="none" stroke="$hand" stroke-width="3" stroke-linecap="round"/>'
      '</svg>',
      width: size, height: size,
    );
  }
}

/// "DialEasy" with "Easy" in green, "TeleCRM" underneath.
class BrandWordmark extends StatelessWidget {
  final bool onDark;
  final double size;
  const BrandWordmark({super.key, this.onDark = false, this.size = 20});

  @override
  Widget build(BuildContext context) {
    final base = onDark ? Colors.white : AppColors.ink;
    final accent = onDark ? AppColors.mintSoft : AppColors.brand;
    return Column(
      mainAxisSize: MainAxisSize.min,
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        Text.rich(TextSpan(children: [
          TextSpan(text: 'Dial', style: TextStyle(color: base)),
          TextSpan(text: 'Easy', style: TextStyle(color: accent)),
        ]), style: TextStyle(fontFamily: kFontFamily, fontWeight: FontWeight.w800,
            fontSize: size, letterSpacing: -0.6, height: 1)),
        const SizedBox(height: 3),
        Text('TeleCRM', style: TextStyle(fontFamily: kFontFamily, fontWeight: FontWeight.w600,
            fontSize: size * .45, letterSpacing: 2, color: onDark ? AppColors.mint : AppColors.text2)),
      ],
    );
  }
}

/// Support agent at a laptop with floating chat, call and chart icons — the
/// web dashboard's header illustration.
class HeroArt extends StatelessWidget {
  final double height;
  const HeroArt({super.key, this.height = 110});

  static const _svg =
    '<svg viewBox="0 0 470 150" xmlns="http://www.w3.org/2000/svg">'
    '<ellipse cx="300" cy="146" rx="170" ry="6" fill="#8fd9b6" opacity=".35"/>'
    '<path d="M40 146h40l-5-30H45z" fill="#fff" stroke="#cbd5e1"/>'
    '<path d="M60 116c-2-22-14-36-28-44 12 16 16 30 18 44zM60 116c3-26 14-44 30-54-10 18-16 36-18 54zM60 116c-8-14-22-20-36-20 12 6 22 12 30 22zM60 116c6-12 18-18 32-16-12 4-22 10-28 18z" fill="#1f9c67"/>'
    '<path d="M60 116c0-30 4-48 10-62-2 18-4 38-4 62z" fill="#2fbf86"/>'
    '<circle cx="130" cy="36" r="20" fill="#0f8a5f"/>'
    '<path d="M122 29h4l2 4-2 1.3a7 7 0 0 0 3.2 3.2l1.3-2 4 2v4a1.6 1.6 0 0 1-1.6 1.6A13 13 0 0 1 120.6 30.6 1.6 1.6 0 0 1 122 29z" fill="#fff"/>'
    '<rect x="176" y="0" width="44" height="34" rx="8" fill="#16a06f"/><path d="M190 34l6 8 6-8z" fill="#16a06f"/>'
    '<path d="M186 11h24M186 17h24M186 23h14" stroke="#fff" stroke-width="2.6" stroke-linecap="round"/>'
    '<rect x="160" y="60" width="44" height="34" rx="8" fill="#1f9c67"/><path d="M170 94l6 8 6-8z" fill="#1f9c67"/>'
    '<rect x="170" y="70" width="24" height="15" rx="3" fill="none" stroke="#fff" stroke-width="2.4"/>'
    '<circle cx="177" cy="77" r="1.6" fill="#fff"/><circle cx="182" cy="77" r="1.6" fill="#fff"/><circle cx="187" cy="77" r="1.6" fill="#fff"/>'
    '<rect x="420" y="40" width="42" height="42" rx="9" fill="#16a06f"/>'
    '<path d="M431 72V62M441 72V54M451 72V48" stroke="#fff" stroke-width="4.5" stroke-linecap="round"/>'
    '<path d="M222 92h80l10 46h-80z" fill="#1c2733"/><circle cx="268" cy="115" r="4" fill="#3a4a5c"/>'
    '<path d="M214 138h120v6H214z" fill="#2a3a4a"/>'
    '<path d="M322 146c0-30 16-50 44-50s44 20 44 50z" fill="#0f8a5f"/>'
    '<path d="M356 98l10 14 10-14z" fill="#fff"/>'
    '<path d="M296 128c14-10 28-16 40-16l6 12c-14 4-28 10-40 16z" fill="#0f8a5f"/>'
    '<rect x="358" y="80" width="16" height="18" rx="6" fill="#f1c6a4"/>'
    '<ellipse cx="366" cy="60" rx="24" ry="27" fill="#f6d0b1"/>'
    '<path d="M340 64c-4-30 12-44 30-44 20 0 32 14 28 40-4-12-14-22-30-24-10 8-20 14-28 28z" fill="#2b1d1a"/>'
    '<path d="M388 50c10 14 12 40 2 64-2-20-4-40-10-56z" fill="#2b1d1a"/>'
    '<circle cx="357" cy="62" r="2.2" fill="#2b1d1a"/><circle cx="375" cy="62" r="2.2" fill="#2b1d1a"/>'
    '<path d="M360 74c4 3 8 3 12 0" fill="none" stroke="#c9735a" stroke-width="2" stroke-linecap="round"/>'
    '<path d="M340 60a26 26 0 0 1 52 0" fill="none" stroke="#1c2733" stroke-width="4"/>'
    '<rect x="335" y="56" width="9" height="16" rx="4" fill="#1c2733"/>'
    '<path d="M340 72c2 8 8 12 16 12" fill="none" stroke="#1c2733" stroke-width="2.4" stroke-linecap="round"/>'
    '</svg>';

  @override
  Widget build(BuildContext context) =>
      SvgPicture.string(_svg, height: height, fit: BoxFit.contain);
}
