import 'dart:async';
import 'dart:convert';

import 'package:fetch_client/fetch_client.dart';
import 'package:flutter/foundation.dart';
import 'package:http/http.dart' as http;

import 'auth_storage.dart';
import 'sse.dart';
import 'models/chat_event.dart';

/// Thrown for any non-2xx gateway response; `statusCode == 401` should route to sign-in.
class ApiException implements Exception {
  final int statusCode;
  final String detail;
  ApiException(this.statusCode, this.detail);

  bool get isUnauthorized => statusCode == 401;

  @override
  String toString() => 'ApiException($statusCode): $detail';
}

/// Talks to the `services/gateway/api.py` REST + SSE surface.
///
/// Web relies on the browser's same-origin cookie jar (`credentials: include` isn't even
/// needed same-origin, but is set defensively) — `X-RI-Client: web` still goes on every
/// state-changing request to satisfy `csrf_guard`. Mobile/desktop has no cookie jar, so the
/// `ri_auth` value captured from `Set-Cookie` on login is replayed as a `Cookie` header.
class ApiClient {
  ApiClient({required this.baseUrl, AuthStorage? authStorage, http.Client? httpClient})
      : _auth = authStorage ?? AuthStorage(),
        _http = httpClient ?? (kIsWeb
            ? FetchClient(
                mode: RequestMode.cors,
                credentials: RequestCredentials.cors,
                streamRequests: false,
              )
            : http.Client());

  final String baseUrl;
  final AuthStorage _auth;
  final http.Client _http;

  void Function()? onUnauthorized;

  Uri _uri(String path, [Map<String, dynamic>? query]) {
    final full = '$baseUrl$path';
    return query == null ? Uri.parse(full) : Uri.parse(full).replace(queryParameters: query.map((k, v) => MapEntry(k, '$v')));
  }

  Future<Map<String, String>> _headers({bool json = true, bool stateChanging = false}) async {
    final headers = <String, String>{};
    if (json) headers['Content-Type'] = 'application/json';
    if (stateChanging) headers['X-RI-Client'] = 'web';
    if (!kIsWeb) {
      final cookie = await _auth.readCookie();
      if (cookie != null) headers['Cookie'] = cookie;
    }
    return headers;
  }

  void _captureCookie(http.BaseResponse response) {
    if (kIsWeb) return;
    final pair = AuthStorage.cookiePairFrom(response.headers['set-cookie']);
    if (pair != null) unawaited(_auth.saveCookie(pair));
  }

  Future<T> _handle<T>(http.Response response, T Function(dynamic json) onOk) async {
    _captureCookie(response);
    if (response.statusCode == 401) {
      onUnauthorized?.call();
      throw ApiException(401, 'Sign in required');
    }
    if (response.statusCode >= 400) {
      String detail = response.body;
      try {
        final decoded = jsonDecode(response.body);
        if (decoded is Map && decoded['detail'] != null) detail = '${decoded['detail']}';
      } catch (_) {}
      throw ApiException(response.statusCode, detail);
    }
    if (response.body.isEmpty) return onOk(null);
    return onOk(jsonDecode(response.body));
  }

  Future<dynamic> get(String path, {Map<String, dynamic>? query}) async {
    final response = await _http.get(_uri(path, query), headers: await _headers(json: false));
    return _handle(response, (j) => j);
  }

  Future<dynamic> post(String path, {Object? body}) async {
    final response = await _http.post(
      _uri(path),
      headers: await _headers(stateChanging: true),
      body: body == null ? null : jsonEncode(body),
    );
    return _handle(response, (j) => j);
  }

  Future<dynamic> patch(String path, {Object? body}) async {
    final response = await _http.patch(
      _uri(path),
      headers: await _headers(stateChanging: true),
      body: body == null ? null : jsonEncode(body),
    );
    return _handle(response, (j) => j);
  }

  Future<dynamic> delete(String path) async {
    final response = await _http.delete(_uri(path), headers: await _headers(json: false, stateChanging: true));
    return _handle(response, (j) => j);
  }

  /// Fetches an authenticated binary resource (preview/figure images) as bytes.
  Future<Uint8List> getBytes(String path, {Map<String, dynamic>? query}) async {
    final response = await _http.get(_uri(path, query), headers: await _headers(json: false));
    _captureCookie(response);
    if (response.statusCode == 401) {
      onUnauthorized?.call();
      throw ApiException(401, 'Sign in required');
    }
    if (response.statusCode >= 400) throw ApiException(response.statusCode, response.body);
    return response.bodyBytes;
  }

  /// Streams `/api/v1/chat` as typed [ChatEvent]s. `body` is the JSON-encoded `ChatRequest`.
  Stream<ChatEvent> streamChat(Map<String, dynamic> body) async* {
    final request = http.Request('POST', _uri('/api/v1/chat'))
      ..headers.addAll(await _headers(stateChanging: true))
      ..body = jsonEncode(body);
    final streamedResponse = await _http.send(request);
    _captureCookie(streamedResponse);
    if (streamedResponse.statusCode == 401) {
      onUnauthorized?.call();
      throw ApiException(401, 'Sign in required');
    }
    if (streamedResponse.statusCode >= 400) {
      final text = await streamedResponse.stream.bytesToString();
      throw ApiException(streamedResponse.statusCode, text);
    }
    final parser = SseParser();
    await for (final chunk in streamedResponse.stream) {
      for (final event in parser.addChunk(chunk)) {
        yield event;
      }
    }
  }

  /// Multipart upload for `/api/v1/ingest` (`file` + optional `route` form fields).
  Future<dynamic> ingestFile(List<int> bytes, String filename, {String? route}) async {
    final request = http.MultipartRequest('POST', _uri('/api/v1/ingest'))
      ..headers.addAll(await _headers(json: false, stateChanging: true))
      ..files.add(http.MultipartFile.fromBytes('file', bytes, filename: filename));
    if (route != null) request.fields['route'] = route;
    final streamedResponse = await _http.send(request);
    final response = await http.Response.fromStream(streamedResponse);
    return _handle(response, (j) => j);
  }

  void close() => _http.close();
}
