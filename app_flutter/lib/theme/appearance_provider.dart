import 'package:flutter_riverpod/flutter_riverpod.dart';

import 'evergreen_theme.dart';

class AppearanceNotifier extends StateNotifier<AppearanceSettings> {
  AppearanceNotifier() : super(const AppearanceSettings());

  void setDensity(AppDensity density) => state = state.copyWith(density: density);
  void setReducedMotion(bool value) => state = state.copyWith(reducedMotion: value);
  void setHighContrast(bool value) => state = state.copyWith(highContrast: value);
}

final appearanceProvider = StateNotifierProvider<AppearanceNotifier, AppearanceSettings>(
  (ref) => AppearanceNotifier(),
);
