// levicrate core menu model. Plain C++17-compatible, no SDK dependency, unit-tested on the host.
#pragma once
#include <algorithm>
#include <cctype>
#include <cmath>
#include <cstdlib>
#include <functional>
#include <sstream>
#include <string>
#include <utility>
#include <vector>

namespace levicrate {

enum class EntryKind { Toggle, SliderInt, SliderFloat, Action };

struct Entry {
    std::string id;
    std::string label;
    EntryKind kind = EntryKind::Toggle;
    double value = 0;
    double defaultValue = 0;
    double minValue = 0;
    double maxValue = 1;
    std::function<void(const Entry&)> onChange;  // Action entries: fired by trigger()
};

inline const char* kindName(EntryKind k) {
    switch (k) {
    case EntryKind::Toggle: return "toggle";
    case EntryKind::SliderInt: return "slider-int";
    case EntryKind::SliderFloat: return "slider-float";
    case EntryKind::Action: return "action";
    }
    return "?";
}

class Menu {
public:
    using Callback = std::function<void(const Entry&)>;

    Menu(std::string id, std::string title) : mId(std::move(id)), mTitle(std::move(title)) {}

    const std::string& id() const { return mId; }
    const std::string& title() const { return mTitle; }
    const std::string& description() const { return mDescription; }
    Menu& description(std::string d) { mDescription = std::move(d); return *this; }

    bool enabled() const { return mEnabled; }
    void setEnabled(bool e) { mEnabled = e; }

    Menu& toggle(const std::string& id, const std::string& label, bool def, Callback cb = {}) {
        return add(id, label, EntryKind::Toggle, def ? 1 : 0, 0, 1, std::move(cb));
    }
    Menu& sliderInt(const std::string& id, const std::string& label, int def, int lo, int hi, Callback cb = {}) {
        return add(id, label, EntryKind::SliderInt, def, lo, hi, std::move(cb));
    }
    Menu& sliderFloat(const std::string& id, const std::string& label, double def, double lo, double hi, Callback cb = {}) {
        return add(id, label, EntryKind::SliderFloat, def, lo, hi, std::move(cb));
    }
    Menu& action(const std::string& id, const std::string& label, Callback cb) {
        return add(id, label, EntryKind::Action, 0, 0, 0, std::move(cb));
    }

    const std::vector<Entry>& entries() const { return mEntries; }
    const std::vector<std::string>& errors() const { return mErrors; }

    const Entry* find(const std::string& id) const {
        for (auto& e : mEntries) if (e.id == id) return &e;
        return nullptr;
    }

    // Sets a value (clamped / rounded per kind). False for unknown id, Action, or NaN.
    bool set(const std::string& id, double v) {
        Entry* e = findMut(id);
        if (!e || e->kind == EntryKind::Action || std::isnan(v)) return false;
        double nv = normalize(*e, v);
        bool changed = nv != e->value;
        e->value = nv;
        if (changed && e->onChange) e->onChange(*e);
        return true;
    }

    // Same as set(), for values that arrive as text (the Mod Menu reports config changes as strings:
    // "true"/"false" or a number). False if the text is not a valid value or the entry is unknown.
    bool setFromString(const std::string& id, const std::string& text) {
        double v;
        if (text == "true") v = 1;
        else if (text == "false") v = 0;
        else {
            if (text.empty()) return false;
            char* endp = nullptr;
            v = std::strtod(text.c_str(), &endp);
            if (*endp != '\0' || std::isinf(v)) return false;
        }
        return set(id, v);
    }

    bool trigger(const std::string& id) {
        Entry* e = findMut(id);
        if (!e || e->kind != EntryKind::Action) return false;
        if (e->onChange) e->onChange(*e);
        return true;
    }

    void reset() {
        for (auto& e : mEntries) if (e.kind != EntryKind::Action) set(e.id, e.defaultValue);
    }

    // {"enabled":true,"id":value,...}  (Action entries are not stored)
    std::string toJson() const {
        std::ostringstream o;
        o.precision(6);
        o << "{\"enabled\":" << (mEnabled ? "true" : "false");
        for (auto& e : mEntries) {
            if (e.kind == EntryKind::Action) continue;
            o << ",\"" << e.id << "\":";
            if (e.kind == EntryKind::Toggle) o << (e.value != 0 ? "true" : "false");
            else if (e.kind == EntryKind::SliderInt) o << static_cast<long long>(e.value);
            else o << e.value;
        }
        o << "}";
        return o.str();
    }

    // Parses the flat object written by toJson(). All-or-nothing: on a syntax error nothing is applied.
    // Unknown keys are ignored so older/newer saves still load.
    bool loadJson(const std::string& text) {
        std::vector<std::pair<std::string, double>> parsed;
        size_t i = 0;
        auto ws = [&] { while (i < text.size() && std::isspace(static_cast<unsigned char>(text[i]))) ++i; };
        ws();
        if (i >= text.size() || text[i] != '{') return false;
        ++i; ws();
        if (i < text.size() && text[i] == '}') return true;
        while (true) {
            ws();
            if (i >= text.size() || text[i] != '"') return false;
            size_t end = text.find('"', i + 1);
            if (end == std::string::npos) return false;
            std::string key = text.substr(i + 1, end - i - 1);
            if (key.find('\\') != std::string::npos) return false;
            i = end + 1; ws();
            if (i >= text.size() || text[i] != ':') return false;
            ++i; ws();
            size_t vs = i;
            while (i < text.size() && text[i] != ',' && text[i] != '}') ++i;
            if (i >= text.size()) return false;
            std::string tok = text.substr(vs, i - vs);
            while (!tok.empty() && std::isspace(static_cast<unsigned char>(tok.back()))) tok.pop_back();
            double v;
            if (tok == "true") v = 1;
            else if (tok == "false") v = 0;
            else {
                if (tok.empty()) return false;
                char* endp = nullptr;
                v = std::strtod(tok.c_str(), &endp);
                if (*endp != '\0' || std::isnan(v) || std::isinf(v)) return false;
            }
            parsed.emplace_back(std::move(key), v);
            if (text[i] == '}') break;
            ++i;
        }
        for (auto& kv : parsed) {
            if (kv.first == "enabled") mEnabled = kv.second != 0;
            else set(kv.first, kv.second);
        }
        return true;
    }

private:
    static bool validId(const std::string& id) {
        if (id.empty() || id == "enabled") return false;
        return std::all_of(id.begin(), id.end(), [](unsigned char c) {
            return std::isalnum(c) || c == '_' || c == '.' || c == '-';
        });
    }

    static double normalize(const Entry& e, double v) {
        switch (e.kind) {
        case EntryKind::Toggle: return v != 0 ? 1 : 0;
        case EntryKind::SliderInt: return std::clamp(std::round(v), e.minValue, e.maxValue);
        case EntryKind::SliderFloat: return std::clamp(v, e.minValue, e.maxValue);
        case EntryKind::Action: return 0;
        }
        return v;
    }

    Menu& add(const std::string& id, const std::string& label, EntryKind k, double def, double lo, double hi, Callback cb) {
        if (!validId(id)) { mErrors.push_back("invalid entry id: '" + id + "'"); return *this; }
        if (find(id)) { mErrors.push_back("duplicate entry id: " + id); return *this; }
        if (lo > hi) { mErrors.push_back("min > max for " + id); return *this; }
        Entry e;
        e.id = id; e.label = label; e.kind = k;
        e.minValue = lo; e.maxValue = hi;
        e.value = e.defaultValue = normalize(e, def);
        e.onChange = std::move(cb);
        mEntries.push_back(std::move(e));
        return *this;
    }

    Entry* findMut(const std::string& id) {
        for (auto& e : mEntries) if (e.id == id) return &e;
        return nullptr;
    }

    std::string mId, mTitle, mDescription;
    bool mEnabled = true;
    std::vector<Entry> mEntries;
    std::vector<std::string> mErrors;
};

}  // namespace levicrate
