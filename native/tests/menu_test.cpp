#include <cmath>
#include <cstdio>
#include <string>
#include <vector>
#include "crate/Backend.hpp"
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

    if (failures == 0) std::printf("menu_test: all checks passed\n");
    return failures ? 1 : 0;
}
