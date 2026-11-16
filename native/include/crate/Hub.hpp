// levicrate Hub: a Better-Bedrock-style mod hub. Many "cards" (Menus) grouped by category, each with an
// Enabled/Disabled switch and its own settings, plus hub-wide Compatibility checks and a Config dump.
// Plain C++17, no SDK dependency, unit-tested on the host.
#pragma once
#include <algorithm>
#include <deque>
#include <set>
#include <sstream>
#include <string>
#include <vector>
#include "crate/Menu.hpp"

namespace levicrate {

class Hub {
public:
    // References stay valid (deque), so callers may keep the returned Menu&.
    Menu& add(const std::string& id, const std::string& title, const std::string& category = "Light") {
        mMenus.emplace_back(id, title);
        mMenus.back().category(category);
        return mMenus.back();
    }

    std::deque<Menu>& menus() { return mMenus; }
    const std::deque<Menu>& menus() const { return mMenus; }

    Menu* find(const std::string& id) {
        for (auto& m : mMenus) if (m.id() == id) return &m;
        return nullptr;
    }

    // Categories in first-seen order, e.g. {"Heavy","Light","Ported"}.
    std::vector<std::string> categories() const {
        std::vector<std::string> out;
        for (auto& m : mMenus)
            if (std::find(out.begin(), out.end(), m.category()) == out.end()) out.push_back(m.category());
        return out;
    }

    std::vector<const Menu*> inCategory(const std::string& cat) const {
        std::vector<const Menu*> out;
        for (auto& m : mMenus) if (m.category() == cat) out.push_back(&m);
        return out;
    }

    // Case-insensitive substring search over title, id and tags.
    std::vector<const Menu*> search(const std::string& q) const {
        auto low = [](std::string s) { for (auto& c : s) c = (char)std::tolower((unsigned char)c); return s; };
        std::string needle = low(q);
        std::vector<const Menu*> out;
        for (auto& m : mMenus) {
            std::string hay = low(m.title() + " " + m.id());
            for (auto& t : m.tags()) hay += " " + low(t);
            if (needle.empty() || hay.find(needle) != std::string::npos) out.push_back(&m);
        }
        return out;
    }

    void setCategoryEnabled(const std::string& cat, bool on) {
        for (auto& m : mMenus) if (m.category() == cat) m.setEnabled(on);
    }
    void setAllEnabled(bool on) { for (auto& m : mMenus) m.setEnabled(on); }
    void resetAll() { for (auto& m : mMenus) { m.reset(); m.setEnabled(true); } }

    // "Compatibility" tab: problems the player should know about. Empty = all good.
    std::vector<std::string> compatibility() const {
        std::vector<std::string> out;
        std::set<std::string> seen;
        for (auto& m : mMenus) {
            if (!seen.insert(m.id()).second) out.push_back("duplicate card id: " + m.id());
            for (auto& e : m.errors()) out.push_back(m.title() + ": " + e);
        }
        return out;
    }

    // "Config" tab: every state/value, grouped by category, one per line (Better Bedrock style):
    //   [Heavy]
    //   $armor_hud true
    //     $armor_hud_x_offset 40
    std::string configText() const {
        std::ostringstream o;
        o.precision(6);
        for (auto& cat : categories()) {
            o << "[" << cat << "]\n";
            for (auto* m : inCategory(cat)) {
                o << "$" << m->id() << " " << (m->enabled() ? "true" : "false") << "\n";
                for (auto& e : m->entries()) {
                    if (e.kind == EntryKind::Action) continue;
                    o << "  $" << m->id() << "_" << e.id << " ";
                    if (e.kind == EntryKind::Toggle) o << (e.value != 0 ? "true" : "false");
                    else if (e.kind == EntryKind::SliderInt) o << static_cast<long long>(e.value);
                    else o << e.value;
                    o << "\n";
                }
            }
        }
        return o.str();
    }

private:
    std::deque<Menu> mMenus;
};

}  // namespace levicrate
