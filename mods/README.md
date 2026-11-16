# Drop your Java mod here

Put one or more `*.jar` files in this folder and push. The **convert** GitHub Actions workflow converts each jar
and uploads a ready-to-import `.levipack` (plus a `PORTING.md` report) as a build artifact.

Locally (needs the Android NDK r28c, cmake, ninja):

    python3 tools/levicrate.py build mods/MyMod.jar --ndk $ANDROID_NDK_HOME -o MyMod.levipack
