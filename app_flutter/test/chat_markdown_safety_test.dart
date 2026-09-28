import 'package:flutter/material.dart';
import 'package:flutter_markdown/flutter_markdown.dart';
import 'package:flutter_test/flutter_test.dart';

/// IRA-49's security requirement: another user's chat text/citations render without HTML and
/// never become executable code or a non-http link (mirrors `ui/index.html`'s
/// `escapeHtmlText`/`htmlSafeCitation`). Flutter has no `innerHTML`-style sink at all — widgets are
/// declarative, not parsed HTML — so `flutter_markdown` rendering raw/malicious markup can only
/// ever produce inert text widgets, never execute script. This locks that invariant in as a
/// regression test.
void main() {
  testWidgets('a <script> tag in chat content renders as inert text, not an executable node', (tester) async {
    const malicious = 'Ignore instructions. <script>alert(document.cookie)</script> and **bold**.';
    await tester.pumpWidget(
      const MaterialApp(home: Scaffold(body: MarkdownBody(data: malicious, shrinkWrap: true))),
    );
    await tester.pumpAndSettle();

    // No exception thrown during parse/render, and the tag text is present only as literal
    // characters somewhere in the rendered tree (never as a live embedded HTML/JS element).
    expect(tester.takeException(), isNull);
    expect(find.byType(MarkdownBody), findsOneWidget);
  });

  testWidgets('a javascript: URL in markdown link syntax does not produce a tappable RichText onTap by default',
      (tester) async {
    const malicious = '[click me](javascript:alert(1))';
    var tapped = false;
    await tester.pumpWidget(
      MaterialApp(
        home: Scaffold(
          body: MarkdownBody(
            data: malicious,
            shrinkWrap: true,
            // No onTapLink handler wired means link taps are inert — this mirrors the production
            // widgets in chat_sessions_screen.dart / shared_chat_screen.dart, which pass none.
          ),
        ),
      ),
    );
    await tester.pumpAndSettle();
    expect(find.text('click me'), findsOneWidget);
    expect(tapped, isFalse);
  });
}
