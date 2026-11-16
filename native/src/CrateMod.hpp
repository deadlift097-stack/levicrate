#pragma once
#include <memory>
#include <pl/Mod.hpp>
#include "crate/Backend.hpp"
#include "crate/Hub.hpp"
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
    void loadSaved();
    void save();

    ll::mod::NativeMod& mSelf;
    std::string configDir() const;
    void dumpConfig();

    levicrate::Hub mHub;
    std::unique_ptr<levicrate::MenuBackend> mBackend;
};
