// ApiClient.errorMessage used to return data['message'] before looking at
// the field errors underneath it. The backend wraps every 400 as
//
//   {"error": "validation_error",
//    "message": "Validation failed.",
//    "detail": {"phone": ["A lead with this phone number already exists."]}}
//
// so every rejected form in the app said "Validation failed." and nothing
// more. An agent adding a lead whose number was already on file had no way
// to learn that, and the sentence explaining it was sitting in `detail`.
//
// The envelopes below are copied from real responses off the running API.
import 'package:dio/dio.dart';
import 'package:flutter_test/flutter_test.dart';

import 'package:dialeasypro/data/services/api_client.dart';

DioException _failure(Object body, {int status = 400}) {
  final req = RequestOptions(path: '/leads/');
  return DioException(
    requestOptions: req,
    response: Response(requestOptions: req, statusCode: status, data: body),
    type: DioExceptionType.badResponse,
  );
}

void main() {
  test('a duplicate lead names the field and the reason', () {
    final msg = ApiClient.errorMessage(_failure({
      'error': 'validation_error',
      'message': 'Validation failed.',
      'detail': {
        'phone': ['A lead with this phone number already exists.'],
      },
    }));

    expect(msg, contains('already exists'));
    expect(msg, contains('phone'));
    expect(msg, isNot('Validation failed.'));
  });

  test('several rejected fields are summarised, not dumped', () {
    final msg = ApiClient.errorMessage(_failure({
      'error': 'validation_error',
      'message': 'Validation failed.',
      'detail': {
        'name': ['This field may not be blank.'],
        'phone': ['Invalid Indian mobile number.'],
        'email': ['Enter a valid email address.'],
      },
    }));

    expect(msg, contains('name'));
    // A toast is not a form: at most two.
    expect('\n'.allMatches(msg).length, lessThanOrEqualTo(1));
  });

  test('non_field_errors is shown without a useless label', () {
    final msg = ApiClient.errorMessage(_failure({
      'message': 'Validation failed.',
      'detail': {
        'non_field_errors': ['Pick a time in the future.'],
      },
    }));

    expect(msg, 'Pick a time in the future.');
    expect(msg, isNot(contains('non_field_errors')));
  });

  test('field errors sent at the top level are still found', () {
    final msg = ApiClient.errorMessage(_failure({
      'sms_text': ['Message text required for SMS campaigns.'],
    }));

    expect(msg, contains('Message text required'));
  });

  test('a plain string detail is passed through', () {
    final msg = ApiClient.errorMessage(_failure(
      {'detail': 'Authentication credentials were not provided.'},
      status: 401,
    ));

    expect(msg, 'Authentication credentials were not provided.');
  });

  test('a message with no field detail is still shown', () {
    final msg = ApiClient.errorMessage(_failure({
      'error': 'not_enrolled',
      'message': 'You are not enrolled as an employee.',
    }));

    expect(msg, 'You are not enrolled as an employee.');
  });

  test('an empty detail map does not swallow the message', () {
    final msg = ApiClient.errorMessage(_failure({
      'message': 'Validation failed.',
      'detail': <String, dynamic>{},
    }));

    expect(msg, 'Validation failed.');
  });

  test('a connection failure reads as one', () {
    final msg = ApiClient.errorMessage(DioException(
      requestOptions: RequestOptions(path: '/leads/'),
      type: DioExceptionType.connectionError,
    ));

    expect(msg.toLowerCase(), contains('connect'));
  });
}
