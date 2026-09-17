// A TagChip with a long label used to demand its full intrinsic width
// wherever it was placed, because its Text had no maxLines and no overflow.
// On the leads list that pushed the row past the right edge — the source
// chip, a priority badge, an optional DND chip and a fixed-width score bar,
// none of them able to give.
//
// Flutter reports an overflow by painting the yellow-and-black stripes AND
// recording a FlutterError, so pumping at a realistic narrow width and
// asserting no exception is a real check rather than a visual one.
import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';

import 'package:dialeasypro/core/widgets/widgets.dart';

/// The widest source label the CRM actually produces.
const _longSource = 'Meta Click-to-WhatsApp';

Widget _host(Widget child, {double width = 320}) => MaterialApp(
      home: Scaffold(
        body: Center(
          child: SizedBox(width: width, child: child),
        ),
      ),
    );

void main() {
  testWidgets('a long label ellipsizes instead of overflowing', (tester) async {
    await tester.pumpWidget(_host(
      // 90px is narrower than the label needs, which is the whole point.
      const SizedBox(width: 90, child: TagChip(label: _longSource)),
    ));

    expect(tester.takeException(), isNull);

    final text = tester.widget<Text>(find.byType(Text));
    expect(text.overflow, TextOverflow.ellipsis);
    expect(text.maxLines, 1);
  });

  testWidgets('the leads row layout survives a narrow phone', (tester) async {
    // The same shape as the lead tile's chips row: a source chip that may
    // shrink, two fixed chips, and a score bar that must keep its width.
    await tester.pumpWidget(_host(
      Row(children: const [
        Flexible(child: TagChip(label: _longSource)),
        SizedBox(width: 6),
        TagChip(label: 'HIGH'),
        SizedBox(width: 6),
        TagChip(label: 'DND'),
        SizedBox(width: 6),
        Spacer(),
        ScoreBar(score: 72),
      ]),
      // Narrower than the content column on a small phone, so the row is
      // genuinely over-subscribed.
      width: 240,
    ));

    expect(tester.takeException(), isNull);
  });

  testWidgets('the dashboard recent-lead row survives a narrow phone',
      (tester) async {
    // A second copy of the same row lives on the home screen. The list tile
    // was fixed first and this one was not, so it kept overflowing — hence
    // the test covering both shapes rather than just the one that was
    // reported.
    await tester.pumpWidget(_host(
      Row(children: const [
        Flexible(child: TagChip(label: _longSource)),
        SizedBox(width: 6),
        TagChip(label: 'WARM'),
        SizedBox(width: 8),
        Spacer(),
        ScoreBar(score: 41),
      ]),
      width: 210,
    ));

    expect(tester.takeException(), isNull);
  });

  testWidgets('an unconstrained chip still measures at its natural width',
      (tester) async {
    // Flexible must not shrink the chip when there is room — every other
    // screen using TagChip relies on it sizing to its content.
    await tester.pumpWidget(_host(
      const Align(
        alignment: Alignment.centerLeft,
        child: TagChip(label: 'CSV'),
      ),
      width: 400,
    ));

    expect(tester.takeException(), isNull);
    final w = tester.getSize(find.byType(TagChip)).width;
    expect(w, lessThan(120), reason: 'a short chip must not stretch');
    expect(w, greaterThan(20));
  });
}
