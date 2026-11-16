#include <cmath>
#include <cstdio>
#include <string>
#include <vector>
#include "crate/Backend.hpp"
#include "crate/Hub.hpp"
#include "crate/Menu.hpp"

static int failures = 0;
#define CHECK(c) do { if (!(c)) { std::printf("FAIL %s:%d  %s\n", __FILE__, __LINE__, #c); ++failures; } } while (0)

using namespace levicrate;

int main() {
    Menu m("t.menu", "Test");
    int fired = 0, actions = 0;
    m.toggle("hud", "HUD", true, [&](const Entry&) { ++fired; });
    m.sliderInt("op", "Opacity", 50, 0, 100);
    m.sliderFloat("sp", "Speed", 1.5, 0.5, 4.0);
    m.action("go", "Go", [&](const Entry&) { ++actions; });
    CHECK(m.errors().empty());
    CHECK(m.entries().size() == 4);

    m.toggle("hud", "dup", false);
    m.toggle("bad id", "x", false);
    m.toggle("enabled", "reserved", false);
    m.sliderInt("rng", "r", 0, 10, 1);
    CHECK(m.errors().size() == 4);
    CHECK(m.entries().size() == 4);

    CHECK(m.set("op", 250));  CHECK(m.find("op")->value == 100);
    CHECK(m.set("op", -3));   CHECK(m.find("op")->value == 0);
    CHECK(m.set("op", 41.6)); CHECK(m.find("op")->value == 42);
    CHECK(m.set("sp", 99));   CHECK(m.find("sp")->value == 4.0);
    CHECK(m.set("hud", 0));   CHECK(fired == 1);
    CHECK(m.set("hud", 0));   CHECK(fired == 1);
    CHECK(!m.set("nope", 1)); CHECK(!m.set("go", 1)); CHECK(!m.set("op", std::nan("")));

    CHECK(m.setFromString("op", "63"));   CHECK(m.find("op")->value == 63);
    CHECK(m.setFromString("sp", "2.5"));  CHECK(m.find("sp")->value == 2.5);
    CHECK(m.setFromString("hud", "true")); CHECK(m.find("hud")->value == 1);
    CHECK(m.setFromString("hud", "false")); CHECK(m.find("hud")->value == 0);
    CHECK(!m.setFromString("op", "abc")); CHECK(!m.setFromString("op", "")); CHECK(!m.setFromString("zzz", "1"));
    CHECK(m.find("op")->value == 63);
    m.set("hud", 0); fired = 1;  // restore state the checks below expect
    CHECK(m.trigger("go")); CHECK(actions == 1);
    CHECK(!m.trigger("hud")); CHECK(!m.trigger("missing"));

    m.set("hud", 1); m.set("op", 77); m.set("sp", 2.25); m.setEnabled(false);
    std::string js = m.toJson();
    Menu n("t.menu", "Test");
    n.toggle("hud", "HUD", false); n.sliderInt("op", "Opacity", 0, 0, 100); n.sliderFloat("sp", "Speed", 1, 0.5, 4.0);
    CHECK(n.loadJson(js));
    CHECK(n.find("hud")->value == 1); CHECK(n.find("op")->value == 77);
    CHECK(n.find("sp")->value == 2.25); CHECK(!n.enabled());

    Menu p("p", "P"); p.sliderInt("op", "O", 10, 0, 100);
    CHECK(!p.loadJson("{\"op\": 99, \"x\": }"));  CHECK(p.find("op")->value == 10);
    CHECK(!p.loadJson("not json"));               CHECK(!p.loadJson("{\"op\":1"));
    CHECK(p.loadJson("{\"op\": 500, \"future\": true}")); CHECK(p.find("op")->value == 100);
    CHECK(p.loadJson("{}"));

    m.reset();
    CHECK(m.find("op")->value == 50); CHECK(m.find("hud")->value == 1);

    std::vector<std::string> lines;
    LoggingBackend lb([&](const std::string& s) { lines.push_back(s); });
    CHECK(lb.publish(m));
    CHECK(lines.size() == 5);
    CHECK(lines[0].find("Test") != std::string::npos);
    CHECK(lines[1].find("HUD [toggle] = on") != std::string::npos);
    lb.withdraw(m);
    CHECK(lines.back().find("withdrawn") != std::string::npos);

    // ---- Hub ----
    Hub hub;
    hub.add("armor", "Armor HUD", "Heavy").tag("All").toggle("big", "Big", false);
    hub.add("inv", "Inventory HUD", "Light").tag("Touch").sliderInt("x", "X", 50, 0, 100);
    hub.add("cps", "CPS Counter", "Heavy");
    CHECK(hub.menus().size() == 3);
    CHECK(hub.categories() == (std::vector<std::string>{"Heavy", "Light"}));
    CHECK(hub.inCategory("Heavy").size() == 2);
    CHECK(hub.search("touch").size() == 1);
    CHECK(hub.search("HUD").size() == 2);
    CHECK(hub.search("").size() == 3);
    Menu* inv = hub.find("inv");
    CHECK(inv != nullptr); inv->set("x", 80);
    hub.setCategoryEnabled("Heavy", false);
    CHECK(!hub.find("armor")->enabled()); CHECK(!hub.find("cps")->enabled()); CHECK(hub.find("inv")->enabled());
    std::string cfg = hub.configText();
    CHECK(cfg.find("[Heavy]") != std::string::npos);
    CHECK(cfg.find("$armor false") != std::string::npos);
    CHECK(cfg.find("  $inv_x 80") != std::string::npos);
    CHECK(hub.compatibility().empty());
    hub.add("armor", "dup", "Light");
    hub.find("inv")->toggle("bad id", "x", false);
    CHECK(hub.compatibility().size() == 2);
    hub.resetAll();
    CHECK(hub.find("armor")->enabled()); CHECK(hub.find("inv")->find("x")->value == 50);

    if (failures == 0) std::printf("menu_test: all checks passed\n");
    return failures ? 1 : 0;
}
