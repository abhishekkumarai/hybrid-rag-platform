import 'dart:convert';

import 'package:app_flutter/api/models/chat_event.dart';
import 'package:app_flutter/api/sse.dart';
import 'package:flutter_test/flutter_test.dart';

List<int> frame(String kind, Map<String, dynamic> data) => utf8.encode('event: $kind\ndata: ${jsonEncode(data)}\n\n');

void main() {
  group('SseParser', () {
    test('parses a single complete frame', () {
      final parser = SseParser();
      final events = parser.addChunk(frame('token', {'token': 'hello'}));
      expect(events, hasLength(1));
      expect(events.single, isA<TokenEvent>());
      expect((events.single as TokenEvent).token, 'hello');
    });

    test('parses multiple frames in one chunk', () {
      final parser = SseParser();
      final bytes = [
        ...frame('session', {'session_id': 's1', 'conversation_id': null}),
        ...frame('token', {'token': 'a'}),
      ];
      final events = parser.addChunk(bytes);
      expect(events, hasLength(2));
      expect(events[0], isA<SessionEvent>());
      expect((events[0] as SessionEvent).sessionId, 's1');
      expect(events[1], isA<TokenEvent>());
    });

    test('buffers a frame split across two chunks', () {
      final parser = SseParser();
      final full = frame('token', {'token': 'split'});
      final mid = full.length ~/ 2;
      expect(parser.addChunk(full.sublist(0, mid)), isEmpty);
      final events = parser.addChunk(full.sublist(mid));
      expect(events, hasLength(1));
      expect((events.single as TokenEvent).token, 'split');
    });

    test('parses a done event with citations', () {
      final parser = SseParser();
      final events = parser.addChunk(frame('done', {
        'refused': false,
        'answer': 'The answer.',
        'citations': [
          {
            'doc_id': 'doc_1',
            'page': 3,
            'bbox': [1.0, 2.0, 3.0, 4.0],
            'snippet': 'snip',
            'formatted_badge': '[doc_1: Page 3]',
          }
        ],
        'top_score': 0.9,
      }));
      expect(events, hasLength(1));
      final done = events.single as DoneEvent;
      expect(done.answer, 'The answer.');
      expect(done.citations.single.docId, 'doc_1');
      expect(done.citations.single.bbox, [1.0, 2.0, 3.0, 4.0]);
    });

    test('a multi-byte character split across chunks is not corrupted', () {
      final parser = SseParser();
      final bytes = frame('token', {'token': '• costs €12,000 📑'});
      final events = <ChatEvent>[];
      // Split inside the 3-byte '•' and again inside the 4-byte emoji.
      final cuts = [bytes.indexOf(0xE2) + 1, bytes.lastIndexOf(0xF0) + 2];
      events.addAll(parser.addChunk(bytes.sublist(0, cuts[0])));
      events.addAll(parser.addChunk(bytes.sublist(cuts[0], cuts[1])));
      events.addAll(parser.addChunk(bytes.sublist(cuts[1])));
      expect((events.single as TokenEvent).token, '• costs €12,000 📑');
    });

    test('parses an error event', () {
      final parser = SseParser();
      final events = parser.addChunk(frame('error', {'error': 'boom'}));
      expect((events.single as ChatErrorEvent).error, 'boom');
    });
  });
}
