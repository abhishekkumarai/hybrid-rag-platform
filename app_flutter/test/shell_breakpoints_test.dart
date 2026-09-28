import 'package:app_flutter/shell/breakpoints.dart';
import 'package:flutter_test/flutter_test.dart';

void main() {
  group('breakpointFor', () {
    test('wide at and above 1200px', () {
      expect(breakpointFor(1200), ShellBreakpoint.wide);
      expect(breakpointFor(1600), ShellBreakpoint.wide);
    });

    test('medium between 600 and 1199px', () {
      expect(breakpointFor(600), ShellBreakpoint.medium);
      expect(breakpointFor(1199), ShellBreakpoint.medium);
    });

    test('narrow below 600px', () {
      expect(breakpointFor(599), ShellBreakpoint.narrow);
      expect(breakpointFor(320), ShellBreakpoint.narrow);
    });
  });
}
