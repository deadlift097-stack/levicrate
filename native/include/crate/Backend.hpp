// Backends turn a Menu into something the player can see.
#pragma once
#include <functional>
#include <sstream>
#include <string>
#include "crate/Menu.hpp"

namespace levicrate {

class MenuBackend {
public:
    virtual ~MenuBackend() = default;
    virtual const char* name() const = 0;
    virtual bool publish(Menu& menu) = 0;   // false = could not show the menu
    virtual void withdraw(Menu& menu) = 0;
};

// Always-available fallback: writes the menu to a log sink.
class LoggingBackend : public MenuBackend {
public:
    using Sink = std::function<void(const std::string&)>;
    explicit LoggingBackend(Sink sink) : mSink(std::move(sink)) {}
    const char* name() const override { return "logging"; }

    bool publish(Menu& menu) override {
        emit("menu '" + menu.title() + "' (" + menu.id() + ") enabled=" + (menu.enabled() ? "yes" : "no"));
        for (auto& e : menu.entries()) emit("  - " + describe(e));
        return true;
    }
    void withdraw(Menu& menu) override { emit("menu '" + menu.title() + "' withdrawn"); }

    static std::string describe(const Entry& e) {
        std::ostringstream o;
        o << e.label << " [" << kindName(e.kind) << "]";
        if (e.kind == EntryKind::Toggle) o << " = " << (e.value != 0 ? "on" : "off");
        else if (e.kind != EntryKind::Action) o << " = " << e.value << " (" << e.minValue << ".." << e.maxValue << ")";
        return o.str();
    }

private:
    void emit(const std::string& s) { if (mSink) mSink(s); }
    Sink mSink;
};

}  // namespace levicrate
