# Native side: what is verified and what is not

Verified on the host (g++ `-Wall -Wextra`, `native/tests/menu_test.cpp`): `crate/Menu.hpp`, `crate/Backend.hpp`
(clamping, validation, JSON save/load, string values from the Mod Menu, actions, logging backend).

Syntax-checked against the **real preloader-android headers (main @ cc08b40)** (clang, C++20, `-Wall -Wextra`, Android/JNI headers stubbed,
no warnings): `CrateMod.*`, `main.cpp`, `crate/PreloaderBackend.hpp`, and the generated `ModPort.cpp` / `Translated.cpp`.
This confirmed the API calls (`ModuleBuilder`, `ButtonBuilder`, `onConfigChanged`, `getConfigDir()`, fmt-style `Logger::debug`).

NOT verified here: linking with the NDK and running inside LeviLauncher on a device (needs a real Android build / game).
The CI workflow (`.github/workflows/build.yml`) is the real check for the link step.

Behavioural notes:
- The Mod Menu reports config edits through `onConfigChanged`; they are applied to the in-memory menu and saved to `config/menu.json`.
- Radio, Color, Keybind and Text entries exist in the SDK but are not wrapped yet.
- **Crash fixed (SIGSEGV in `registerModule`)**: tag 0.2.3's `ModuleInfo` is 224 bytes, the launcher's runtime (SDK `main`) reads a
  272-byte struct (extra `onKeybind`) and copies garbage past the end of the mod's smaller object. The build is now pinned to
  SDK commit `cc08b40` and a `static_assert` stops builds against an SDK without `onKeybind`. If a future launcher changes
  the struct again, set `-DCRATE_SDK_TAG=<commit the launcher was built from>`; `-DCRATE_PL_MENU=OFF` builds the log-only fallback
  (no menu, no `registerModule` call).
- Toolchain: NDK r28c, arm64-v8a only, C++20.
