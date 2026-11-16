# Native side: what is verified and what is not

Verified on the host (g++ `-Wall -Wextra`, `native/tests/menu_test.cpp`): `crate/Menu.hpp`, `crate/Backend.hpp`
(clamping, validation, JSON save/load, string values from the Mod Menu, actions, logging backend).

Syntax-checked against the **real preloader-android 0.2.3 headers** (clang, C++20, `-Wall -Wextra`, Android/JNI headers stubbed,
no warnings): `CrateMod.*`, `main.cpp`, `crate/PreloaderBackend.hpp`, and the generated `ModPort.cpp` / `Translated.cpp`.
This confirmed the API calls (`ModuleBuilder`, `ButtonBuilder`, `onConfigChanged`, `getConfigDir()`, fmt-style `Logger::debug`).

NOT verified here: linking with the NDK and running inside LeviLauncher on a device (needs a real Android build / game).
The CI workflow (`.github/workflows/build.yml`) is the real check for the link step.

Behavioural notes:
- The Mod Menu reports config edits through `onConfigChanged`; they are applied to the in-memory menu and saved to `config/menu.json`.
- Radio, Color, Keybind and Text entries exist in the SDK but are not wrapped yet.
- Build against the same preloader SDK tag as your launcher (`-DCRATE_SDK_TAG=...`, default 0.2.3). A mismatched `ModuleInfo`
  layout can crash inside `registerModule()`; if that happens build with `-DCRATE_PL_MENU=OFF` to use the log-only fallback.
- Toolchain: NDK r28c, arm64-v8a only, C++20.
