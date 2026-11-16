#pragma once
#include <memory>
#include <pl/Mod.hpp>
#include "crate/Backend.hpp"
#include "crate/Menu.hpp"

class CrateMod {
public:
    static CrateMod& instance();
    CrateMod();

    [[nodiscard]] ll::mod::NativeMod& getSelf() const { return mSelf; }

    bool load();
    bool enable();
    bool disable();
    bool unload();

private:
    void buildMenu();
    void logLine(const std::string& line);
    std::string savePath() const;
    void loadSaved();
    void save();

    ll::mod::NativeMod& mSelf;
    levicrate::Menu mMenu;
    std::unique_ptr<levicrate::MenuBackend> mBackend;
};
