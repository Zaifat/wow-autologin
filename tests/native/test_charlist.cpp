// Native test for CharListJson.h — built with the same MSVC toolchain as the
// DLL by tests/test_native.py. Prints the JSON it builds so the Python side
// can parse and check it, and fails on any self-check it can do in C++.
#include "../../awesome_wotlk_src/src/AwesomeWotlkLib/CharListJson.h"

#include <cstdio>
#include <cstring>

static int failures = 0;

static void expect(bool ok, const char* what)
{
    if (!ok) {
        std::fprintf(stderr, "FAIL %s\n", what);
        ++failures;
    }
}

int main(int argc, char** argv)
{
    // The row that killed the game: every number at its widest, a long
    // Cyrillic name, and a full 10-character account.
    std::vector<CharListJson::Row> rows;
    for (int i = 0; i < 10; ++i) {
        CharListJson::Row r;
        r.name = "\xD0\x97\xD0\xB0\xD0\xB9\xD1\x84\xD0\xB0\xD1\x82";   // Зайфат
        r.level = 255; r.cls = 255; r.race = 255; r.gender = 255;
        rows.push_back(r);
    }
    CharListJson::Row odd;
    odd.name = "Quote\"Back\\slash\ttab";
    rows.push_back(odd);

    std::string json = CharListJson::build(
        "account_with_a_long_login_name",
        "WoW Circle 3.3.5a x100 [MSK] \"special\"",
        18446744073709551615ULL, rows);

    expect(json.size() > 11 * 44, "all rows written");
    expect(json.back() == '\n', "ends with a newline");
    expect(json.find("\\\"") != std::string::npos, "quotes escaped");
    expect(json.find("\\u0009") != std::string::npos, "control char escaped");

    // empty list and empty strings are fine too
    std::string empty = CharListJson::build("", "", 0, {});
    expect(empty == "{\"account\":\"\",\"realm\":\"\",\"at\":0,\"chars\":[]}\n",
           "empty list");

    // file names: safe characters only, never empty
    expect(CharListJson::fileSafe("acc.name-1") == "acc.name-1", "safe kept");
    expect(CharListJson::fileSafe("a b/c:d") == "a_b_c_d", "unsafe replaced");
    expect(CharListJson::fileSafe("") == "_", "empty login");
    expect(CharListJson::fnv1a("") == 2166136261u, "fnv offset basis");
    expect(CharListJson::fnv1a("a") == 0xe40c292cu, "fnv of 'a'");

    if (argc > 1 && std::strcmp(argv[1], "--print") == 0)
        std::fwrite(json.data(), 1, json.size(), stdout);
    return failures ? 1 : 0;
}
