// APP-M10: the mobile quick-import now goes through the server import, so
// pasted rows become a CSV file, and unusable lines are reported.

import 'package:flutter_test/flutter_test.dart';

import 'package:dialeasypro/features/leads/lead_import_screen.dart';

void main() {
  test('usable lines become rows; the rest are listed by line number', () {
    final parsed = parseImportText(
      'Rahul, 9876543210, rahul@x.com, Mumbai, Wants a 2BHK, near metro\n'
      '\n'
      'No phone here\n'
      'Priya, 12345\n'
      'Asha, +91 98123 00001\n',
    );

    expect(parsed.rows.map((r) => r.name), ['Rahul', 'Asha']);
    expect(parsed.rows.first.requirement, 'Wants a 2BHK, near metro');
    expect(parsed.skipped, [3, 4]);
  });

  test('the CSV has a header and quotes cells that need it', () {
    final csv = buildImportCsv(const [
      ImportRow(name: 'Rahul "RS" Sharma', phone: '9876543210', requirement: '2BHK, near metro'),
    ]);

    expect(csv.split('\n').first, 'name,phone,email,city,requirement');
    expect(csv, contains('"Rahul ""RS"" Sharma",9876543210,,,"2BHK, near metro"'));
  });
}
