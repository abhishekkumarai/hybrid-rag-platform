import 'dart:convert';

import 'models/chat_event.dart';

/// Parses the gateway's SSE wire format (`services/gateway/chat_pipeline.py::to_sse`):
/// blank-line-delimited frames of `event: <kind>\ndata: <json>\n\n`.
///
/// Feed raw byte chunks as they arrive; frames are only emitted once a full
/// blank-line-terminated block has been buffered, so a frame split across two
/// network chunks still parses correctly.
class SseParser {
  final StringBuffer _buffer = StringBuffer();

  // Stateful: a multi-byte character (•, €, emoji) split across two network chunks is held until
  // its remaining bytes arrive, instead of each half decoding to U+FFFD.
  late final ByteConversionSink _decoder =
      const Utf8Decoder(allowMalformed: true).startChunkedConversion(StringConversionSink.fromStringSink(_buffer));

  List<ChatEvent> addChunk(List<int> bytes) {
    _decoder.add(bytes);
    return _drainCompleteFrames();
  }

  List<ChatEvent> _drainCompleteFrames() {
    final events = <ChatEvent>[];
    final text = _buffer.toString();
    final frames = text.split('\n\n');
    // The last element is either '' (buffer ended exactly on a frame boundary)
    // or a partial frame still being received — keep it buffered.
    final complete = frames.sublist(0, frames.length - 1);
    _buffer
      ..clear()
      ..write(frames.last);

    for (final frame in complete) {
      final event = _parseFrame(frame);
      if (event != null) events.add(event);
    }
    return events;
  }

  ChatEvent? _parseFrame(String frame) {
    String? kind;
    final dataLines = <String>[];
    for (final rawLine in frame.split('\n')) {
      final line = rawLine.startsWith('\r') ? rawLine.substring(1) : rawLine;
      if (line.startsWith('event:')) {
        kind = line.substring('event:'.length).trim();
      } else if (line.startsWith('data:')) {
        dataLines.add(line.substring('data:'.length).trim());
      }
    }
    if (kind == null || dataLines.isEmpty) return null;
    final dataJson = dataLines.join('\n');
    final decoded = jsonDecode(dataJson);
    final data = decoded is Map<String, dynamic> ? decoded : <String, dynamic>{};
    return ChatEvent.fromSse(kind: kind, data: data);
  }
}
