// The lead screen used to print the raw DioException ("This exception was
// thrown because the response has a status code of 404…") — what an agent saw
// on tapping a notification for a lead since reassigned or deleted.

import 'package:dio/dio.dart';
import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';

import 'package:dialeasypro/features/leads/lead_detail_screen.dart';

DioException _status(int code) {
  final options = RequestOptions(path: '/leads/952/');
  return DioException(
    requestOptions: options,
    type: DioExceptionType.badResponse,
    response: Response(requestOptions: options, statusCode: code, data: {'error': 'not_found'}),
  );
}

Future<void> _pump(WidgetTester tester, Object error, {VoidCallback? onRetry}) async {
  await tester.pumpWidget(MaterialApp(home: LeadUnavailableView(error: error, onRetry: onRetry ?? () {})));
  // Let the empty-state entrance animation finish.
  await tester.pump(const Duration(seconds: 2));
}

void main() {
  testWidgets('a lead that is gone is explained in words', (tester) async {
    await _pump(tester, _status(404));

    expect(find.text('This lead is not available'), findsOneWidget);
    expect(find.textContaining('reassigned to another agent or deleted'), findsOneWidget);
    expect(find.text('Go to my leads'), findsOneWidget);
    expect(find.textContaining('DioException'), findsNothing);
  });

  testWidgets('any other failure offers a retry, without the raw exception', (tester) async {
    var retried = false;
    await _pump(
      tester,
      DioException(requestOptions: RequestOptions(path: '/leads/1/'), type: DioExceptionType.connectionError),
      onRetry: () => retried = true,
    );

    expect(find.text('Could not load this lead'), findsOneWidget);
    expect(find.textContaining('DioException'), findsNothing);
    await tester.tap(find.text('Try again'));
    expect(retried, isTrue);
  });
}
