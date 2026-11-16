// In-game Mod Menu backend. Only compiled when LEVICRATE_PL_MENU=1 (Android build).
// Written against the public docs of the Mod Menu API:
//   https://levimc.org/LeviLamina/developer_guides/android/api/mod_menu/
// Calls marked [DOC] are copied from documented examples; [ASSUMED] are not shown in the docs
// (see native/README.md - each has a one-line fix if the SDK differs).
#pragma once
#include <pl/ModMenu.hpp>
#include <string>
#include <string_view>
#include <vector>
#include "crate/Backend.hpp"

namespace levicrate {

class PreloaderBackend : public MenuBackend {
public:
    explicit PreloaderBackend(std::string modId) : mModId(std::move(modId)) {}
    const char* name() const override { return "pl::modmenu"; }

    bool publish(Menu& menu) override {
        using namespace pl::modmenu;
        Menu* m = &menu;

        auto builder = ModuleBuilder(menu.id(), menu.title())              // [DOC]
                           .modId(mModId)                                  // [DOC]
                           .description(menu.description())                // [DOC]
                           .defaultEnabled(menu.enabled())                 // [DOC]
                           .onToggle([m](std::string_view, bool on) {      // [DOC] signature (string_view, bool)
                               m->setEnabled(on);
                           });

        for (const Entry& e : menu.entries()) {
            switch (e.kind) {
            case EntryKind::Toggle:                                         // [DOC] config(key,label,type,default,min,max)
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
        if (!builder.registerModule()) return false;                        // [DOC] returns bool

        for (const Entry& e : menu.entries()) {
            if (e.kind != EntryKind::Action) continue;
            const std::string buttonId = menu.id() + "." + e.id;
            bool ok = ButtonBuilder(buttonId, e.label)                      // [DOC]
                          .modId(mModId)                                    // [DOC]
                          .moduleId(menu.id())                              // [DOC]
                          .label(e.label)                                   // [DOC]
                          .androidKeyCode(0)                                // [DOC]
                          .behavior(ButtonBehavior::Click)                  // [DOC]
                          .onEvent([m, id = e.id](std::string_view, ButtonEvent, float) {  // [DOC] signature
                              m->trigger(id);                               // [ASSUMED] Click behavior only reports clicks
                          })
                          .registerButton();                                // [DOC]
            if (ok) mButtons.push_back(buttonId);
        }
        mModules.push_back(menu.id());
        return true;
    }

    void withdraw(Menu&) override {
        for (auto& b : mButtons) pl::modmenu::unregisterButton(b);          // [ASSUMED] takes the id string
        for (auto& m : mModules) pl::modmenu::unregisterModule(m);          // [ASSUMED] takes the id string
        mButtons.clear();
        mModules.clear();
    }

private:
    std::string mModId;
    std::vector<std::string> mModules, mButtons;
};

}  // namespace levicrate
