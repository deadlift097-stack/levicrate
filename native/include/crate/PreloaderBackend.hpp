// In-game Mod Menu backend. Only compiled when LEVICRATE_PL_MENU=1 (Android build).
// Written against the public docs of the Mod Menu API:
//   https://levimc.org/LeviLamina/developer_guides/android/api/mod_menu/
// Checked against preloader-android 0.2.3 (include/pl/ModMenu.hpp).
#pragma once
#include <pl/ModMenu.hpp>
#include <functional>
#include <string>
#include <string_view>
#include <vector>
#include "crate/Backend.hpp"

// The launcher's libpreloader.so reads ModuleInfo *by value layout*. SDK tag 0.2.3 ModuleInfo has no `onKeybind`
// (224 bytes); the launcher runtime built from SDK `main` reads it (272 bytes) and crashes with SIGSEGV inside
// pl::modmenu::registerModule when the mod was compiled against the older, shorter struct. Refuse to build that.
static_assert(requires(pl::modmenu::ModuleInfo i) { i.onKeybind; },
              "preloader SDK too old: ModuleInfo has no onKeybind. Build with CRATE_SDK_TAG set to the SDK commit your "
              "launcher uses (default in CMakeLists.txt), otherwise the mod crashes in registerModule().");

namespace levicrate {

class PreloaderBackend : public MenuBackend {
public:
    // onChanged: called after the player edits a config value or toggles the module (use it to save).
    explicit PreloaderBackend(std::string modId, std::function<void()> onChanged = {})
        : mModId(std::move(modId)), mOnChanged(std::move(onChanged)) {}
    const char* name() const override { return "pl::modmenu"; }

    bool publish(Menu& menu) override {
        using namespace pl::modmenu;
        Menu* m = &menu;

        auto builder = ModuleBuilder(menu.id(), menu.title())
                           .modId(mModId)
                           .description(cardDescription(menu))
                           .defaultEnabled(menu.enabled())
                           .onToggle([this, m](std::string_view, bool on) {
                               m->setEnabled(on);
                               if (mOnChanged) mOnChanged();
                           })
                           .onConfigChanged([this, m](std::string_view, std::string_view key, std::string_view value) {
                               m->setFromString(std::string(key), std::string(value));   // in-game edits are read back
                               if (mOnChanged) mOnChanged();
                           });

        for (const Entry& e : menu.entries()) {
            switch (e.kind) {
            case EntryKind::Toggle:
                builder.config(e.id, e.label, ConfigType::Toggle, e.value != 0 ? "true" : "false", "0", "1");
                break;
            case EntryKind::SliderInt:
                builder.config(e.id, e.label, ConfigType::SliderInt, std::to_string(static_cast<long long>(e.value)),
                               std::to_string(static_cast<long long>(e.minValue)), std::to_string(static_cast<long long>(e.maxValue)));
                break;
            case EntryKind::SliderFloat:
                builder.config(e.id, e.label, ConfigType::SliderFloat, std::to_string(e.value),
                               std::to_string(e.minValue), std::to_string(e.maxValue));
                break;
            case EntryKind::Action: break;                                  // actions become floating buttons below
            }
        }
        if (!builder.registerModule()) return false;

        for (const Entry& e : menu.entries()) {
            if (e.kind != EntryKind::Action) continue;
            const std::string buttonId = menu.id() + "." + e.id;
            bool ok = ButtonBuilder(buttonId, e.label)
                          .modId(mModId)
                          .moduleId(menu.id())
                          .label(e.label)
                          .androidKeyCode(0)
                          .behavior(ButtonBehavior::Click)
                          .onEvent([m, id = e.id](std::string_view, ButtonEvent ev, float) {
                              if (ev == ButtonEvent::Click) m->trigger(id);
                          })
                          .registerButton();
            if (ok) mButtons.push_back(buttonId);
        }
        mModules.push_back(menu.id());
        return true;
    }

    void withdraw(Menu&) override {
        for (auto& b : mButtons) pl::modmenu::unregisterButton(b);        
        for (auto& m : mModules) pl::modmenu::unregisterModule(m);        
        mButtons.clear();
        mModules.clear();
    }

private:
    // Card text: "[Heavy] All, Touch - description"
    static std::string cardDescription(const Menu& m) {
        std::string d = "[" + m.category() + "]";
        for (size_t i = 0; i < m.tags().size(); ++i) d += (i ? ", " : " ") + m.tags()[i];
        if (!m.description().empty()) d += " - " + m.description();
        return d;
    }
    std::string mModId;
    std::function<void()> mOnChanged;
    std::vector<std::string> mModules, mButtons;
};

}  // namespace levicrate
