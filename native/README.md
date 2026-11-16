# Native side: what is verified and what is not

Verified here (host g++ -Wall -Wextra, `native/tests/menu_test.cpp`): `crate/Menu.hpp`, `crate/Backend.hpp`
(clamping, validation, JSON save/load, actions, logging backend).

NOT compiled here (no Android NDK / SDK access in the authoring environment): `CrateMod.*`, `main.cpp`,
`crate/PreloaderBackend.hpp`. They were written against the public docs
(<https://levimc.org/LeviLamina/developer_guides/android/api/mod_menu/>, `.../api/mod/`) and the template README.
The first CI run (`.github/workflows/build.yml`) is the real check. If it fails, these are the only
suspects, each a one-line fix:

| # | Where | Assumption | If wrong |
|---|-------|-----------|----------|
| 1 | `CrateMod::logLine` | `Logger::debug` is fmt-style (`debug("{}", s)`) | pass `s` directly |
| 2 | `CrateMod::savePath` | `getConfigDir()` converts to `std::filesystem::path` | use the type it returns |
| 3 | `PreloaderBackend::publish` | builder methods return a chainable `ModuleBuilder`, `config()` can be called on it afterwards | collect entries first, build in one chain |
| 4 | `PreloaderBackend::withdraw` | `unregisterModule(id)` / `unregisterButton(id)` take the id string | match the header |
| 5 | Button callback | `ButtonBehavior::Click` only reports clicks | filter on `ButtonEvent` |

Known limits (not documented in the SDK pages I could read): the docs show no callback for slider/toggle
*config value* changes, so in-game edits of config entries are not read back; only the module-level
on/off (`onToggle`) and button clicks are. Values persisted in `config/menu.json` are fed in as defaults.
Radio and Color entries exist in the SDK but are not wrapped yet.

ABI warning: build against the same preloader SDK tag as your launcher (`-DCRATE_SDK_TAG=...`, default 0.2.2,
the tag the official template pins). Third-party reports describe crashes inside `registerModule()` when a mod
is compiled against an older `ModuleInfo` layout. If that happens, build with `-DCRATE_PL_MENU=OFF` to run on
the log-only fallback.
