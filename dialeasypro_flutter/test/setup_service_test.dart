// ============================================================
// Brand detection for first-run setup.
//
// Build.MANUFACTURER and Build.BRAND are not a fixed vocabulary — a Redmi
// reports "Xiaomi", a POCO can report either, an iQOO reports "vivo", and
// Infinix reports "INFINIX" or "Transsion" depending on the ROM. Getting this
// wrong shows the agent instructions for the wrong Phone app, which is worse
// than the generic ones, so the mapping is pinned here.
// ============================================================
import 'package:dialeasypro/core/services/setup_service.dart';
import 'package:flutter_test/flutter_test.dart';

void main() {
  group('brand detection', () {
    test('Samsung', () {
      expect(SetupService.guideFor('samsung SM-A546E').brand, PhoneBrand.samsung);
    });

    test('Xiaomi family — Redmi and POCO report inconsistently', () {
      for (final id in ['Xiaomi', 'Redmi 22120RN86I', 'POCO M6 Pro', 'xiaomi poco']) {
        expect(SetupService.guideFor(id).brand, PhoneBrand.xiaomi, reason: id);
      }
    });

    test('Vivo family includes iQOO', () {
      expect(SetupService.guideFor('vivo V2312').brand, PhoneBrand.vivo);
      expect(SetupService.guideFor('iQOO Neo').brand, PhoneBrand.vivo);
    });

    test('Oppo, Realme and OnePlus share ColorOS', () {
      for (final id in ['OPPO CPH2557', 'realme RMX3771', 'OnePlus CPH2581']) {
        expect(SetupService.guideFor(id).brand, PhoneBrand.oppoRealme, reason: id);
      }
    });

    test('Transsion family — Infinix, Tecno, itel', () {
      for (final id in ['INFINIX Infinix X6831', 'TECNO Spark', 'itel A70']) {
        expect(SetupService.guideFor(id).brand, PhoneBrand.transsion, reason: id);
      }
    });

    test('Motorola', () {
      expect(SetupService.guideFor('motorola moto g84 5G').brand, PhoneBrand.motorola);
    });

    test('unknown brands still get usable generic steps', () {
      final guide = SetupService.guideFor('Nothing A065');
      expect(guide.brand, PhoneBrand.other);
      expect(guide.recordingSteps, isNotEmpty);
    });
  });

  group('background-restriction flag', () {
    test('is set for the ROMs that freeze background apps', () {
      for (final id in ['Xiaomi', 'vivo', 'realme', 'OPPO', 'INFINIX']) {
        expect(SetupService.guideFor(id).needsAutoStart, isTrue, reason: id);
      }
    });

    test('is not set where battery optimisation alone is enough', () {
      for (final id in ['samsung', 'motorola', 'Google Pixel 8']) {
        expect(SetupService.guideFor(id).needsAutoStart, isFalse, reason: id);
      }
    });
  });

  group('guidance content', () {
    test('every brand gets at least two concrete steps', () {
      const ids = ['samsung', 'Xiaomi', 'vivo', 'realme', 'INFINIX', 'motorola',
                   'Google', 'unknown-oem'];
      for (final id in ids) {
        expect(SetupService.guideFor(id).recordingSteps.length,
            greaterThanOrEqualTo(2),
            reason: id);
      }
    });

    test('devices that may have no recorder say so', () {
      // Setting an expectation the phone cannot meet is how a support ticket
      // starts. Pixel and Motorola guidance must name the fallback.
      for (final id in ['Google Pixel', 'motorola']) {
        expect(SetupService.guideFor(id).recordingSteps.join(' ').toLowerCase(),
            contains('microphone'),
            reason: id);
      }
    });

    test('matching is case insensitive', () {
      expect(SetupService.guideFor('SAMSUNG').brand,
          SetupService.guideFor('samsung').brand);
    });
  });
}
