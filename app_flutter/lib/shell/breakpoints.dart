enum ShellBreakpoint { wide, medium, narrow }

/// ≥1200px: 3 panes. 600-1199px: rail + end-drawer inspector. <600px: drawer + stacked pages.
ShellBreakpoint breakpointFor(double width) {
  if (width >= 1200) return ShellBreakpoint.wide;
  if (width >= 600) return ShellBreakpoint.medium;
  return ShellBreakpoint.narrow;
}
