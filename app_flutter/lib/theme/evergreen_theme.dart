import 'package:flutter/material.dart';
import 'package:google_fonts/google_fonts.dart';

/// The Evergreen palette (`ui/stitch_workspace/DESIGN-evergreen.md`, IRA-41). Values are pinned
/// exactly — never substitute Stitch's auto-generated tones.
class EvergreenColors {
  static const canvas = Color(0xFFFBFBF9);
  static const surface = Color(0xFFFFFFFF);
  static const fill = Color(0xFFF5F5F2);
  static const border = Color(0xFFE7E5E0);
  static const ink = Color(0xFF1C1917);
  static const inkSecondary = Color(0xFF57534E);
  static const metadata = Color(0xFF78716C);
  static const caption = Color(0xFF8A8580);
  static const primary = Color(0xFF1F6B52);
  static const primaryHover = Color(0xFF175340);
  static const primaryTint = Color(0xFFE9F2EE);
  static const primaryTintBorder = Color(0xFFD1E3DA);

  static const confident = Color(0xFF1F8A5B);
  static const confidentTint = Color(0xFFEAF6EF);
  static const ambiguous = Color(0xFFB7791F);
  static const ambiguousTint = Color(0xFFFBF3E4);
  static const refused = Color(0xFFB4534F);
  static const refusedTint = Color(0xFFF9ECEC);

  static const folderSage = Color(0xFFE9F2EE);
  static const folderSageIcon = Color(0xFF1F6B52);
  static const folderSky = Color(0xFFE8F0F8);
  static const folderSkyIcon = Color(0xFF3F7CAC);
  static const folderSand = Color(0xFFFBF3E4);
  static const folderSandIcon = Color(0xFFB7791F);
  static const folderRose = Color(0xFFF9ECEC);
  static const folderRoseIcon = Color(0xFFB4534F);
}

class EvergreenRadii {
  static const panel = 12.0;
  static const control = 8.0;
  static const chip = 4.0;
}

/// Density / accessibility appearance settings (IRA-47), independent of the palette above.
enum AppDensity { compact, comfortable, spacious }

class AppearanceSettings {
  final AppDensity density;
  final bool reducedMotion;
  final bool highContrast;

  const AppearanceSettings({
    this.density = AppDensity.comfortable,
    this.reducedMotion = false,
    this.highContrast = false,
  });

  AppearanceSettings copyWith({AppDensity? density, bool? reducedMotion, bool? highContrast}) =>
      AppearanceSettings(
        density: density ?? this.density,
        reducedMotion: reducedMotion ?? this.reducedMotion,
        highContrast: highContrast ?? this.highContrast,
      );

  double get scale => switch (density) {
        AppDensity.compact => 0.85,
        AppDensity.comfortable => 1.0,
        AppDensity.spacious => 1.15,
      };
}

/// A ThemeExtension carrying answer-state and folder tints that don't map to Material's
/// ColorScheme roles.
@immutable
class EvergreenExtension extends ThemeExtension<EvergreenExtension> {
  const EvergreenExtension({
    required this.confident,
    required this.confidentTint,
    required this.ambiguous,
    required this.ambiguousTint,
    required this.refused,
    required this.refusedTint,
    required this.caption,
    required this.metadata,
    required this.appearance,
  });

  final Color confident;
  final Color confidentTint;
  final Color ambiguous;
  final Color ambiguousTint;
  final Color refused;
  final Color refusedTint;
  final Color caption;
  final Color metadata;
  final AppearanceSettings appearance;

  static const light = EvergreenExtension(
    confident: EvergreenColors.confident,
    confidentTint: EvergreenColors.confidentTint,
    ambiguous: EvergreenColors.ambiguous,
    ambiguousTint: EvergreenColors.ambiguousTint,
    refused: EvergreenColors.refused,
    refusedTint: EvergreenColors.refusedTint,
    caption: EvergreenColors.caption,
    metadata: EvergreenColors.metadata,
    appearance: AppearanceSettings(),
  );

  @override
  EvergreenExtension copyWith({
    Color? confident,
    Color? confidentTint,
    Color? ambiguous,
    Color? ambiguousTint,
    Color? refused,
    Color? refusedTint,
    Color? caption,
    Color? metadata,
    AppearanceSettings? appearance,
  }) =>
      EvergreenExtension(
        confident: confident ?? this.confident,
        confidentTint: confidentTint ?? this.confidentTint,
        ambiguous: ambiguous ?? this.ambiguous,
        ambiguousTint: ambiguousTint ?? this.ambiguousTint,
        refused: refused ?? this.refused,
        refusedTint: refusedTint ?? this.refusedTint,
        caption: caption ?? this.caption,
        metadata: metadata ?? this.metadata,
        appearance: appearance ?? this.appearance,
      );

  @override
  EvergreenExtension lerp(ThemeExtension<EvergreenExtension>? other, double t) {
    if (other is! EvergreenExtension) return this;
    return EvergreenExtension(
      confident: Color.lerp(confident, other.confident, t)!,
      confidentTint: Color.lerp(confidentTint, other.confidentTint, t)!,
      ambiguous: Color.lerp(ambiguous, other.ambiguous, t)!,
      ambiguousTint: Color.lerp(ambiguousTint, other.ambiguousTint, t)!,
      refused: Color.lerp(refused, other.refused, t)!,
      refusedTint: Color.lerp(refusedTint, other.refusedTint, t)!,
      caption: Color.lerp(caption, other.caption, t)!,
      metadata: Color.lerp(metadata, other.metadata, t)!,
      appearance: t < 0.5 ? appearance : other.appearance,
    );
  }
}

extension EvergreenExtensionAccess on BuildContext {
  EvergreenExtension get evergreen => Theme.of(this).extension<EvergreenExtension>() ?? EvergreenExtension.light;
}

/// JetBrains Mono, for doc ids, page refs, scores, latencies, model names and chunk text.
/// DESIGN-evergreen.md's "mono 12/20" is a size/line-height pair — `height` is a multiplier of
/// `fontSize`, so 12/20 is `20 / 12`.
TextStyle monoStyle({double fontSize = 12, FontWeight weight = FontWeight.w500, Color? color}) =>
    GoogleFonts.jetBrainsMono(
      fontSize: fontSize,
      fontWeight: weight,
      color: color,
      height: 20 / 12,
      fontFeatures: const [FontFeature.tabularFigures()],
    );

/// DESIGN-evergreen.md's type scale: headings 36/24/20/16, body 14/22, small 13/18 (size/line-height).
TextTheme _evergreenTextTheme(TextTheme base) => base.copyWith(
      displaySmall: base.displaySmall?.copyWith(fontSize: 36, height: 40 / 36, fontWeight: FontWeight.w700),
      headlineMedium: base.headlineMedium?.copyWith(fontSize: 24, height: 32 / 24, fontWeight: FontWeight.w700),
      headlineSmall: base.headlineSmall?.copyWith(fontSize: 20, height: 28 / 20, fontWeight: FontWeight.w600),
      titleLarge: base.titleLarge?.copyWith(fontSize: 16, height: 24 / 16, fontWeight: FontWeight.w600),
      bodyMedium: base.bodyMedium?.copyWith(fontSize: 14, height: 22 / 14),
      bodySmall: base.bodySmall?.copyWith(fontSize: 13, height: 18 / 13),
    );

/// Double focus ring (DESIGN-evergreen.md inputs: `#1F6B52` border + 2px `#E9F2EE` outline).
/// `InputDecorationTheme.focusedBorder` only paints one ring, so this border paints a second,
/// wider stroke in the tint color behind the normal one.
class _DoubleRingBorder extends OutlineInputBorder {
  const _DoubleRingBorder()
      : super(
          borderRadius: const BorderRadius.all(Radius.circular(EvergreenRadii.control)),
          borderSide: const BorderSide(color: EvergreenColors.primary, width: 2),
        );

  @override
  void paint(
    Canvas canvas,
    Rect rect, {
    double? gapStart,
    double gapExtent = 0.0,
    double gapPercentage = 0.0,
    TextDirection? textDirection,
  }) {
    final outerRect = rect.inflate(2);
    final outerRRect = borderRadius.resolve(textDirection).toRRect(outerRect);
    canvas.drawRRect(
      outerRRect,
      Paint()
        ..color = EvergreenColors.primaryTint
        ..style = PaintingStyle.stroke
        ..strokeWidth = 2,
    );
    super.paint(canvas, rect, gapStart: gapStart, gapExtent: gapExtent, gapPercentage: gapPercentage, textDirection: textDirection);
  }
}

ThemeData buildEvergreenTheme({AppearanceSettings appearance = const AppearanceSettings()}) {
  final base = GoogleFonts.dmSansTextTheme();
  final highContrastBorder = appearance.highContrast ? EvergreenColors.ink : EvergreenColors.border;

  return ThemeData(
    useMaterial3: true,
    brightness: Brightness.light,
    scaffoldBackgroundColor: EvergreenColors.canvas,
    canvasColor: EvergreenColors.canvas,
    fontFamily: GoogleFonts.dmSans().fontFamily,
    textTheme: _evergreenTextTheme(base.apply(bodyColor: EvergreenColors.ink, displayColor: EvergreenColors.ink)),
    colorScheme: const ColorScheme.light(
      primary: EvergreenColors.primary,
      onPrimary: Colors.white,
      surface: EvergreenColors.surface,
      onSurface: EvergreenColors.ink,
      secondaryContainer: EvergreenColors.primaryTint,
      onSecondaryContainer: EvergreenColors.primary,
      error: EvergreenColors.refused,
    ),
    dividerColor: highContrastBorder,
    cardTheme: CardThemeData(
      color: EvergreenColors.surface,
      elevation: 0,
      shape: RoundedRectangleBorder(
        borderRadius: BorderRadius.circular(EvergreenRadii.panel),
        side: BorderSide(color: highContrastBorder),
      ),
    ),
    // DESIGN-evergreen.md popover/modal shadow (`0 8px 24px rgba(28,25,23,.08), 0 2px 6px
    // rgba(28,25,23,.04)`) approximated as a single Material elevation shadow — Flutter's
    // DialogTheme has no multi-layer box-shadow support.
    dialogTheme: DialogThemeData(
      backgroundColor: EvergreenColors.surface,
      surfaceTintColor: Colors.transparent,
      elevation: 12,
      shadowColor: EvergreenColors.ink.withValues(alpha: 0.12),
      shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(EvergreenRadii.panel)),
    ),
    inputDecorationTheme: InputDecorationTheme(
      filled: true,
      fillColor: EvergreenColors.surface,
      border: OutlineInputBorder(
        borderRadius: BorderRadius.circular(EvergreenRadii.control),
        borderSide: BorderSide(color: highContrastBorder),
      ),
      focusedBorder: const _DoubleRingBorder(),
    ),
    elevatedButtonTheme: ElevatedButtonThemeData(
      style: ElevatedButton.styleFrom(
        backgroundColor: EvergreenColors.primary,
        foregroundColor: Colors.white,
        minimumSize: Size(64, 40 * appearance.scale),
        shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(EvergreenRadii.control)),
        textStyle: GoogleFonts.dmSans(fontSize: 14, fontWeight: FontWeight.w500),
      ).copyWith(
        backgroundColor: WidgetStateProperty.resolveWith(
          (states) => states.contains(WidgetState.hovered) ? EvergreenColors.primaryHover : EvergreenColors.primary,
        ),
      ),
    ),
    outlinedButtonTheme: OutlinedButtonThemeData(
      style: OutlinedButton.styleFrom(
        foregroundColor: EvergreenColors.ink,
        side: BorderSide(color: highContrastBorder),
        minimumSize: Size(64, 40 * appearance.scale),
        shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(EvergreenRadii.control)),
      ).copyWith(
        backgroundColor: WidgetStateProperty.resolveWith(
          (states) => states.contains(WidgetState.hovered) ? EvergreenColors.primaryTint : null,
        ),
        side: WidgetStateProperty.resolveWith(
          (states) => BorderSide(color: states.contains(WidgetState.hovered) ? EvergreenColors.primary : highContrastBorder),
        ),
      ),
    ),
    // DESIGN-evergreen.md ghost button: `#78716C` (metadata) text, no fill/border.
    textButtonTheme: TextButtonThemeData(
      style: TextButton.styleFrom(
        foregroundColor: EvergreenColors.metadata,
        minimumSize: Size(64, 40 * appearance.scale),
        shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(EvergreenRadii.control)),
      ),
    ),
    pageTransitionsTheme: appearance.reducedMotion
        ? const PageTransitionsTheme(builders: {
            TargetPlatform.android: FadeUpwardsPageTransitionsBuilder(),
            TargetPlatform.iOS: FadeUpwardsPageTransitionsBuilder(),
            TargetPlatform.windows: FadeUpwardsPageTransitionsBuilder(),
            TargetPlatform.macOS: FadeUpwardsPageTransitionsBuilder(),
            TargetPlatform.linux: FadeUpwardsPageTransitionsBuilder(),
          })
        : null,
    extensions: [EvergreenExtension.light.copyWith(appearance: appearance)],
  );
}
