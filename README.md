# levicrate

Builds **.levipack** containers for LeviLauncher (Android) native mods, ships an in-game **mod menu**, and converts
**Java mods** into a ready-to-build native workspace.

Built from the layout described in the
[LeviLauncher Android mod template](https://github.com/QYCottage/levilauncher-android-mod-template)
(manifest fields, `PL_REGISTER_MOD` lifecycle, `.levipack` = zip of `<id>/{manifest.json, lib<name>.so, ...}`). No code was copied from any earlier project.

## Java -> levipack: automatic C++ rewrite

```
python3 tools/levicrate.py convert MyMod.jar -o workspace --mc "1.21.*"
```
`convert` reads the jar's bytecode and **translates it to C++ automatically** (`workspace/src/Translated.cpp`), plus metadata
(fabric/quilt/forge/neoforge/bukkit), assets, `ModPort.cpp` (menu buttons that run translated `static void` methods) and `PORTING.md`.

**What is translated automatically:** methods built from int/long/float/double/boolean/byte/char/short, locals, `if`/loops/`goto`,
static fields (incl. `<clinit>` initialisers), calls between translated methods, and a `java.lang.Math` subset. Java semantics are
kept (wrap-around overflow, shift masking, saturating float->int casts, NaN comparisons, `Math.round`).
**Proof:** `tests/test_translate.py` compiles real Java with javac, translates the `.class`, runs the C++ and requires output
**identical to the JVM's** (98 lines of edge cases).

**What cannot be automatic:** anything touching objects, arrays, strings, instance calls, `switch`, `try/catch`, lambdas or Minecraft
classes. Those methods become explicit stubs (`levicrate::junsupported`, observable via `levicrate::faultHandler()`) and are listed in
`PORTING.md` with the exact reason. Minecraft calls need a hand-found hook or signature for the Bedrock binary; no tool can guess it.
Methods that call a stub are flagged too.

Then build (add your hooks in `workspace/src/ModPort.cpp`; `convert` never overwrites it):

```
cmake -S . -B build -G Ninja -DCMAKE_TOOLCHAIN_FILE=$ANDROID_NDK/build/cmake/android.toolchain.cmake \
      -DANDROID_ABI=arm64-v8a -DANDROID_PLATFORM=android-28 -DANDROID_STL=c++_shared -DCRATE_WORKSPACE=$PWD/workspace
cmake --build build --target levi_package      # -> build/<id>-<version>-arm64-v8a.levipack
```
Already have a compiled library? `python3 tools/levicrate.py pack --workspace workspace --so libmymod.so`.

## Mod menu
`native/include/crate/Menu.hpp`: toggles, int/float sliders, action buttons, validation, clamping, JSON persistence
(`config/menu.json`). Backends: `PreloaderBackend` (real `pl::modmenu`) with automatic fall-back to `LoggingBackend`.

## Tests
`python3 -m unittest discover -s tests` and `cmake -S . -B b && cmake --build b && ctest --test-dir b`.
**Read `native/README.md`**: it lists which C++ files are host-tested and which still need their first Android build.
