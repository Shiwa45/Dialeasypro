// The Answered / Not answered buttons on the call-outcome screens were
// ChoiceChips whose selected colour was a pale tint or the same grey as an
// unselected chip — tapping one looked as if nothing had happened. The chosen
// one is now solid (green / red) and the other stays outlined.

import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';

import 'package:dialeasypro/core/theme/colors.dart';
import 'package:dialeasypro/features/calls/answered_toggle.dart';

Color? _fill(WidgetTester tester, String label) {
  final box = tester.widget<AnimatedContainer>(
    find.ancestor(of: find.text(label), matching: find.byType(AnimatedContainer)),
  );
  return (box.decoration as BoxDecoration).color;
}

void main() {
  Future<void> pump(WidgetTester tester, bool? value, {ValueChanged<bool>? onChanged}) =>
      tester.pumpWidget(MaterialApp(
        home: Scaffold(body: AnsweredToggle(value: value, onChanged: onChanged ?? (_) {})),
      ));

  testWidgets('nothing chosen: both outlined', (tester) async {
    await pump(tester, null);

    expect(_fill(tester, 'Answered'), AppColors.white);
    expect(_fill(tester, 'Not answered'), AppColors.white);
  });

  testWidgets('Answered chosen: solid green, the other outlined', (tester) async {
    await pump(tester, true);
    await tester.pumpAndSettle();

    expect(_fill(tester, 'Answered'), AppColors.success);
    expect(_fill(tester, 'Not answered'), AppColors.white);
  });

  testWidgets('Not answered chosen: solid red, the other outlined', (tester) async {
    await pump(tester, false);
    await tester.pumpAndSettle();

    expect(_fill(tester, 'Not answered'), AppColors.error);
    expect(_fill(tester, 'Answered'), AppColors.white);
  });

  testWidgets('tapping reports the choice', (tester) async {
    bool? chosen;
    await pump(tester, null, onChanged: (v) => chosen = v);

    await tester.tap(find.text('Not answered'));
    expect(chosen, isFalse);
    await tester.tap(find.text('Answered'));
    expect(chosen, isTrue);
  });
}
