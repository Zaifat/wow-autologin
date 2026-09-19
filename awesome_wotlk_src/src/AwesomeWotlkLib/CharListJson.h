#pragma once
// Builds the character-list JSON the manager imports. Kept free of any game
// client types so it can be unit-tested on its own (tests/native).
//
// Everything is appended to std::string — no fixed-size buffers. An earlier
// version formatted each row with sprintf_s into a 32-byte buffer; rows are
// longer than that, and sprintf_s answers an overflow by terminating the
// process, which closed the game on the character list.

#include <cstdio>
#include <string>
#include <vector>

namespace CharListJson {

struct Row {
    std::string name;
    unsigned level = 0;
    unsigned cls = 0;
    unsigned race = 0;
    unsigned gender = 0;
};

inline void appendEscaped(std::string& out, const char* s)
{
    for (const unsigned char* p = (const unsigned char*)s; p && *p; ++p) {
        unsigned char c = *p;
        if (c == '"' || c == '\\') {
            out += '\\';
            out += (char)c;
        } else if (c < 0x20) {
            char buf[8];
            std::snprintf(buf, sizeof(buf), "\\u%04x", c);
            out += buf;
        } else {
            out += (char)c;     // UTF-8 bytes pass through untouched
        }
    }
}

inline std::string build(const char* login, const char* realm,
                         unsigned long long at, const std::vector<Row>& rows)
{
    std::string json = "{\"account\":\"";
    appendEscaped(json, login);
    json += "\",\"realm\":\"";
    appendEscaped(json, realm);
    json += "\",\"at\":" + std::to_string(at) + ",\"chars\":[";
    for (size_t i = 0; i < rows.size(); ++i) {
        const Row& r = rows[i];
        if (i) json += ",";
        json += "{\"name\":\"";
        appendEscaped(json, r.name.c_str());
        json += "\",\"level\":" + std::to_string(r.level)
              + ",\"class\":" + std::to_string(r.cls)
              + ",\"race\":" + std::to_string(r.race)
              + ",\"gender\":" + std::to_string(r.gender) + "}";
    }
    json += "]}\n";
    return json;
}

inline std::string fileSafe(const char* s)
{
    std::string out;
    for (const char* p = s; p && *p; ++p) {
        char c = *p;
        bool ok = (c >= 'a' && c <= 'z') || (c >= 'A' && c <= 'Z')
               || (c >= '0' && c <= '9') || c == '-' || c == '.';
        out += ok ? c : '_';
    }
    return out.empty() ? std::string("_") : out;
}

// Realm names are often Cyrillic and would all collapse to "____" in a file
// name, so the realm part of the name is a hash; the real name is inside.
inline unsigned fnv1a(const char* s)
{
    unsigned h = 2166136261u;
    for (const unsigned char* p = (const unsigned char*)s; p && *p; ++p) {
        h ^= *p;
        h *= 16777619u;
    }
    return h;
}

}  // namespace CharListJson
