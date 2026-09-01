# StockLog Native Mobile TypeScript fix — 2026-08-26

The React Native native rewrite previously used CSS-like font weights such as `650`, `750`, `850`, and `950`.
React Native 0.86 / TypeScript accepts only the supported React Native `fontWeight` literals (100-step weights, plus named weights).

Those invalid literals caused each affected `StyleSheet.create()` call to fail its `NamedStyles` constraint. Once that happened, TypeScript widened style entries to `ViewStyle | TextStyle | ImageStyle`, which produced hundreds of cascading errors at otherwise-correct `<View>`, `<Text>`, `<Pressable>`, and `<TextInput>` style props.

Applied fixes:

- `650` -> `600`
- `750` -> `700`
- `850` -> `800`
- `950` -> `900`
- Added `mobile/scripts/check-native-styles.mjs`.
- Added `npm run check:styles` before `npm run typecheck` in both `restart-mobile.sh` and `build-mobile.sh`.
- The validator also rejects accidental WebView-era runtime references in the native source tree.

Affected source files were the same 13 files reported by the TypeScript error summary.
