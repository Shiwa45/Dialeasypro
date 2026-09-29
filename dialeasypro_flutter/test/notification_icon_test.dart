// APP-C1: the notification plugin refuses to start when its default icon is
// not a drawable in the app, and every reminder then fails silently. It
// pointed at '@mipmap/ic_launcher', which never existed. This pins the name in
// NotificationService to a real drawable file.

import 'dart:io';

import 'package:flutter_test/flutter_test.dart';

void main() {
  test('the notification icon NotificationService asks for exists', () {
    final source = File('lib/core/services/notification_service.dart').readAsStringSync();
    final match = RegExp(r"AndroidInitializationSettings\('([^']+)'\)").firstMatch(source);
    expect(match, isNotNull, reason: 'no AndroidInitializationSettings found');

    final name = match!.group(1)!;
    expect(name.startsWith('@mipmap/'), isFalse, reason: 'the app has no mipmap resources');

    final plain = name.replaceFirst('@drawable/', '');
    final res = Directory('android/app/src/main/res');
    final found = res
        .listSync()
        .whereType<Directory>()
        .where((d) => d.path.split(Platform.pathSeparator).last.startsWith('drawable'))
        .any((d) => File('${d.path}/$plain.xml').existsSync() || File('${d.path}/$plain.png').existsSync());
    expect(found, isTrue, reason: 'drawable "$plain" is missing from android/app/src/main/res');
  });
}
