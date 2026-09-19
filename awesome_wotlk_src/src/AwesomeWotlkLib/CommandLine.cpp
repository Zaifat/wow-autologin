#include "CommandLine.h"
#include "Hooks.h"
#include "GameClient.h"
#include "Utils.h"
#include "CharListJson.h"
#include <shellapi.h>
#include <bcrypt.h>
#include <stdio.h>
#include <stdarg.h>
#include <string>
#include <vector>
#include <map>
#include <fstream>

#pragma comment(lib, "bcrypt.lib")


static std::vector<std::string> s_commandLine;

// ── autologin state ───────────────────────────────────────────────────────────
// Every callback in this file is invoked from the client's render thread, so
// plain statics are enough — no interlocked access needed.
static int   s_characterIndex = -1;   // slot of the requested character, -1 = unknown
static bool  s_autologinDone  = false;// latched once the world has been reached
static bool  s_selectIssued   = false;
static int   s_enterTries     = 0;
static DWORD s_selectTick     = 0;
static DWORD s_enterTick      = 0;
static bool  s_tokenSubmitted = false;
static bool  s_charEnumLogged = false;
static std::string s_targetCharacter;  // who we are currently trying to enter
static bool  s_targetInit     = false;
static std::string s_pendingSwitch;    // set from Lua by the in-game addon
static DWORD s_pendingTick     = 0;    // when the switch was requested
static bool  s_switchMode      = false;// re-armed by a switch, not by the launcher
static DWORD s_rearmTick       = 0;
static bool  s_listSinceSwitch = false;// a character list arrived after the request

// Wait this long after selecting the slot before asking to enter the world —
// the click has to be applied client-side first.
static const DWORD kSelectSettleMs = 700;
// EnterWorld is asynchronous (auth handshake + loading screen). Retrying it
// while the first attempt is still in flight makes the server drop the freshly
// created session and the player lands back on character select — which is
// exactly the bug this timeout exists to avoid. Only a character-select screen
// that is still visibly up this long after the attempt gets another try.
static const DWORD kEnterRetryMs  = 20000;
static const int   kMaxEnterTries = 3;
// A switch request only stays valid for the logout it was made for: the game's
// countdown is 20 s, plus the trip back to character select. After that it is
// stale, and must not hijack some later, unrelated logout.
static const DWORD kSwitchTtlMs   = 60000;
// After logging out, the client still holds the OLD character list until the
// server sends a fresh one. Wait for it (or this long) before picking a slot.
static const DWORD kFreshListWaitMs = 5000;


static void writeLog(const char* fmt, ...)
{
    static FILE* f = NULL;
    static bool tried = false;
    if (!tried) {
        tried = true;
        char path[MAX_PATH];
        if (GetModuleFileNameA(NULL, path, MAX_PATH)) {
            char* slash = strrchr(path, '\\');
            if (slash) *(slash + 1) = '\0';
            strcat_s(path, MAX_PATH, "autologin.log");
            f = fopen(path, "w");
        }
        if (!f) f = fopen("autologin.log", "w");
    }
    if (!f) return;
    SYSTEMTIME st;
    GetLocalTime(&st);
    fprintf(f, "[%02d:%02d:%02d.%03d] ", st.wHour, st.wMinute, st.wSecond, st.wMilliseconds);
    va_list args;
    va_start(args, fmt);
    vfprintf(f, fmt, args);
    va_end(args);
    fputc('\n', f);
    fflush(f);
}


// ── JSON file fallback ────────────────────────────────────────────────────────
// When Wow.exe is launched by something that doesn't forward argv (e.g. an
// external GUI loader), read autologin parameters from a JSON file placed
// next to Wow.exe by the launcher. The file is deleted after first read
// because it contains the password.

static std::map<std::string, std::string> s_jsonParams;
static bool s_jsonLoaded = false;


static void parseJsonString(const char*& p, const char* end, std::string& out)
{
    out.clear();
    if (p >= end || *p != '"') return;
    ++p;
    while (p < end && *p != '"') {
        if (*p == '\\' && p + 1 < end) {
            char c = p[1];
            switch (c) {
                case '"':  out += '"';  break;
                case '\\': out += '\\'; break;
                case '/':  out += '/';  break;
                case 'n':  out += '\n'; break;
                case 't':  out += '\t'; break;
                case 'r':  out += '\r'; break;
                case 'b':  out += '\b'; break;
                case 'f':  out += '\f'; break;
                default:   out += c;    break;
            }
            p += 2;
        } else {
            out += *p++;
        }
    }
    if (p < end && *p == '"') ++p;
}


static void skipJsonWs(const char*& p, const char* end)
{
    while (p < end && (*p == ' ' || *p == '\t' || *p == '\n' || *p == '\r'))
        ++p;
}


static void loadJsonParams()
{
    if (s_jsonLoaded) return;
    s_jsonLoaded = true;

    char path[MAX_PATH] = {0};
    if (!GetModuleFileNameA(NULL, path, MAX_PATH)) return;
    char* slash = strrchr(path, '\\');
    if (!slash) return;
    *(slash + 1) = '\0';
    strcat_s(path, MAX_PATH, "autologin.json");

    std::ifstream f(path, std::ios::binary | std::ios::ate);
    if (!f) return;
    std::streamsize sz = f.tellg();
    if (sz <= 0 || sz > 8192) return; // sanity
    f.seekg(0, std::ios::beg);
    std::vector<char> buf((size_t)sz);
    if (!f.read(buf.data(), sz)) return;
    f.close();

    const char* p = buf.data();
    const char* end = p + sz;
    skipJsonWs(p, end);
    if (p >= end || *p != '{') return;
    ++p; skipJsonWs(p, end);
    while (p < end && *p != '}') {
        std::string key, val;
        parseJsonString(p, end, key);
        skipJsonWs(p, end);
        if (p >= end || *p != ':') break;
        ++p; skipJsonWs(p, end);
        parseJsonString(p, end, val);
        if (!key.empty()) s_jsonParams[key] = val;
        skipJsonWs(p, end);
        if (p < end && *p == ',') { ++p; skipJsonWs(p, end); }
    }

    writeLog("[json] loaded %d params", (int)s_jsonParams.size());
    // Wipe file — it contains the password
    DeleteFileA(path);
}


static const char* getParam(const char* item)
{
    // 1. Command-line argv
    for (int i = 1; (i + 1) < (int)s_commandLine.size(); i++) {
        const char* key = s_commandLine[i].c_str();
        if (char c = *(key++); c == '-' || c == '/') {
            if (key[0] == '-') ++key;
            if (strcmp(key, item) == 0)
                return s_commandLine[i + 1].c_str();
        }
    }

    // 2. autologin.json next to Wow.exe (fallback for external loaders)
    loadJsonParams();
    auto it = s_jsonParams.find(item);
    if (it != s_jsonParams.end() && !it->second.empty())
        return it->second.c_str();

    return NULL;
}


// Case-insensitive for ASCII, exact for everything else — which is what we
// want: the client hands us the name in UTF-8 and so does the launcher, and
// _stricmp would only ever fold the ASCII half of a Cyrillic name anyway.
// The character we should enter. Starts out as whatever the launcher asked
// for and is replaced when the in-game addon requests a switch.
static const char* currentTarget()
{
    if (!s_targetInit) {
        s_targetInit = true;
        if (const char* c = getParam("character"))
            s_targetCharacter = c;
    }
    return s_targetCharacter.empty() ? NULL : s_targetCharacter.c_str();
}


static bool sameCharacterName(const char* actual, const char* expected)
{
    if (!(actual && expected && *actual && *expected))
        return false;
    return _stricmp(actual, expected) == 0;
}


static const char* kSelectFuncs[] = {
    "CharacterSelect_SelectCharacter",
    "SelectCharacter",
    NULL,
};


// Compile and run a Lua source chunk. Chunks talk back through globals — the
// client's Lua build gives us no convenient way to read return values back.
static bool runLuaChunk(lua_State* L, const char* src)
{
    lua_getglobal(L, "loadstring");
    if (!lua_isfunction(L, -1)) { lua_pop(L, 1); return false; }
    lua_pushstring(L, src);
    if (lua_pcall(L, 1, 1, 0) != 0) { lua_pop(L, 1); return false; }
    if (!lua_isfunction(L, -1)) { lua_pop(L, 1); return false; }
    if (lua_pcall(L, 0, 0, 0) != 0) { lua_pop(L, 1); return false; }
    return true;
}


// True only while the character-select screen is actually up. `CharacterSelect`
// is a GlueXML-only global: the moment EnterWorld takes hold the glue Lua state
// is torn down and the global disappears, which is how we tell "the enter went
// through, we're loading" from "nothing happened, we're still sitting here".
// `CharacterSelect` is a GlueXML-only global. The glue and the game world run
// in separate Lua states, so it exists exactly while we are on the glue screens.
static bool glueAlive(lua_State* L)
{
    if (!L) return false;
    lua_getglobal(L, "CharacterSelect");
    bool alive = !lua_isnil(L, -1);
    lua_pop(L, 1);
    return alive;
}


static bool atCharacterSelect(lua_State* L)
{
    if (!glueAlive(L)) return false;

    // The glue can be alive with a different screen in front (realm list, token
    // dialog), so ask the frame itself.
    static const char* probe =
        "AutoLoginAtCharSelect = nil "
        "local f = CharacterSelect "
        "if f and f.IsVisible and f:IsVisible() then AutoLoginAtCharSelect = 1 end ";
    if (!runLuaChunk(L, probe)) return false;

    lua_getglobal(L, "AutoLoginAtCharSelect");
    bool visible = !lua_isnil(L, -1);
    lua_pop(L, 1);
    return visible;
}


static bool callLuaFunction0(lua_State* L, const char* fnName)
{
    lua_getglobal(L, fnName);
    if (!lua_isfunction(L, -1)) {
        writeLog("[lua] %s: not a function (type=%d)", fnName, lua_type(L, -1));
        lua_pop(L, 1);
        return false;
    }
    int rc = lua_pcall(L, 0, 0, 0);
    if (rc != 0) {
        writeLog("[lua] %s(): pcall rc=%d", fnName, rc);
        lua_pop(L, 1);
        return false;
    }
    writeLog("[lua] %s(): ok", fnName);
    return true;
}


static bool callLuaSelect(lua_State* L, int oneBasedIdx)
{
    for (int k = 0; kSelectFuncs[k]; k++) {
        const char* fn = kSelectFuncs[k];
        lua_getglobal(L, fn);
        if (!lua_isfunction(L, -1)) {
            lua_pop(L, 1);
            continue;
        }
        lua_pushnumber(L, (lua_Number)oneBasedIdx);
        int rc = lua_pcall(L, 1, 0, 0);
        if (rc != 0) {
            writeLog("[lua] %s(%d): pcall rc=%d", fn, oneBasedIdx, rc);
            lua_pop(L, 1);
            continue;
        }
        writeLog("[lua] %s(%d): ok", fn, oneBasedIdx);
        return true;
    }
    writeLog("[lua] no select function found");
    return false;
}


// ── TOTP (RFC 6238) ───────────────────────────────────────────────────────────
// We compute the 6-digit code on demand in the DLL so it can never expire
// between launcher click and TokenEnterDialog appearing.

static bool base32Decode(const char* in, std::vector<uint8_t>& out)
{
    out.clear();
    int buf = 0, bits = 0;
    for (const char* p = in; *p; ++p) {
        char c = *p;
        if (c == ' ' || c == '-' || c == '=') continue;
        int v;
        if (c >= 'A' && c <= 'Z')      v = c - 'A';
        else if (c >= 'a' && c <= 'z') v = c - 'a';
        else if (c >= '2' && c <= '7') v = 26 + (c - '2');
        else return false;
        buf = (buf << 5) | v;
        bits += 5;
        if (bits >= 8) {
            bits -= 8;
            out.push_back((uint8_t)((buf >> bits) & 0xFF));
        }
    }
    return !out.empty();
}


static bool hmacSha1(const uint8_t* key, DWORD keyLen,
                     const uint8_t* msg, DWORD msgLen,
                     uint8_t outDigest[20])
{
    BCRYPT_ALG_HANDLE hAlg = NULL;
    BCRYPT_HASH_HANDLE hHash = NULL;
    bool ok = false;
    if (BCryptOpenAlgorithmProvider(&hAlg, BCRYPT_SHA1_ALGORITHM, NULL,
                                    BCRYPT_ALG_HANDLE_HMAC_FLAG) != 0)
        return false;
    if (BCryptCreateHash(hAlg, &hHash, NULL, 0,
                         (PUCHAR)key, keyLen, 0) == 0
        && BCryptHashData(hHash, (PUCHAR)msg, msgLen, 0) == 0
        && BCryptFinishHash(hHash, outDigest, 20, 0) == 0)
        ok = true;
    if (hHash) BCryptDestroyHash(hHash);
    BCryptCloseAlgorithmProvider(hAlg, 0);
    return ok;
}


// Current 30-second TOTP step (RFC 6238 counter).
static uint64_t totpStep()
{
    FILETIME ft;
    GetSystemTimeAsFileTime(&ft);
    ULARGE_INTEGER ull;
    ull.LowPart = ft.dwLowDateTime;
    ull.HighPart = ft.dwHighDateTime;
    // FILETIME = 100-ns intervals since 1601; Unix = seconds since 1970
    uint64_t unixSec = (ull.QuadPart - 116444736000000000ULL) / 10000000ULL;
    return unixSec / 30;
}


static std::string computeTotp(const std::string& base32Secret, uint64_t counter)
{
    std::vector<uint8_t> key;
    if (!base32Decode(base32Secret.c_str(), key)) return "";

    uint8_t msg[8];
    for (int i = 7; i >= 0; --i) {
        msg[i] = (uint8_t)(counter & 0xFF);
        counter >>= 8;
    }

    uint8_t digest[20];
    if (!hmacSha1(key.data(), (DWORD)key.size(), msg, 8, digest))
        return "";

    int off = digest[19] & 0x0F;
    uint32_t code = ((digest[off] & 0x7F) << 24)
                  | ((digest[off + 1] & 0xFF) << 16)
                  | ((digest[off + 2] & 0xFF) << 8)
                  | (digest[off + 3] & 0xFF);
    code %= 1000000;

    char buf[8];
    sprintf_s(buf, "%06u", code);
    return std::string(buf);
}


static std::string getCurrentToken()
{
    // Prefer fresh TOTP from secret (works regardless of launcher-to-dialog delay)
    const char* secret = getParam("totp_secret");
    if (secret && *secret) {
        // This runs every frame while the login screens are up. The code only
        // changes every 30 s, so compute (and log) once per step instead of
        // doing HMAC-SHA1 and a log line on every single frame.
        static uint64_t s_step = ~0ULL;
        static std::string s_code;
        uint64_t step = totpStep();
        if (step != s_step) {
            s_step = step;
            s_code = computeTotp(secret, step);
            // Never log the code itself — autologin.log sits next to Wow.exe.
            if (s_code.empty())
                writeLog("[totp] failed to compute from secret");
            else
                writeLog("[totp] new code for this 30s window");
        }
        if (!s_code.empty())
            return s_code;
    }
    // Legacy fallback: static pre-computed token
    const char* tok = getParam("token");
    if (tok && *tok) return std::string(tok);
    return "";
}


static void tryTokenSubmit()
{
    if (s_tokenSubmitted) return;

    // Compute fresh on every call — TOTP code rotates every 30s, and we don't
    // know when the dialog will actually appear after launcher click.
    std::string fresh = getCurrentToken();
    if (fresh.empty()) return;
    const char* token = fresh.c_str();
    for (const char* p = token; *p; ++p)
        if (*p < '0' || *p > '9') return;

    lua_State* L = GetLuaState();
    if (!L) return;

    // Pass token via global so we don't have to escape it inside the script.
    lua_pushstring(L, token);
    lua_setglobal(L, "AutoLoginToken");

    // Comprehensive dialog handling — tries every plausible mechanism.
    // Result codes (set into AutoLoginTokenStage) help diagnose which path
    // succeeded. AutoLoginTokenDone = 1 marks successful submission.
    static const char* script =
        "AutoLoginTokenDone = nil "
        "AutoLoginTokenStage = 0 "
        "local code = AutoLoginToken "
        "local d = TokenEnterDialog or AccountLoginTokenDialog "
        "if not (code and d and d.IsVisible and d:IsVisible()) then return end "
        "AutoLoginTokenStage = 1 "

        // Find an edit box for the token
        "local e = TokenEnterDialogBackgroundEdit or TokenEnterDialogEdit "
        "         or AccountLoginTokenEdit or _G['TokenEnterDialogEditBox'] "
        "if e and e.SetText then e:SetText(code) end "
        "AutoLoginTokenStage = 2 "

        // Method A: simulate Enter key on the edit box
        "if e and e.GetScript then "
        "  local fn = e:GetScript('OnEnterPressed') "
        "  if fn then fn(e); AutoLoginTokenDone=1; AutoLoginTokenStage=10; return end "
        "end "

        // Method B: standard WoW glue accept handler
        "if type(TokenEnterDialog_OnAccept) == 'function' then "
        "  TokenEnterDialog_OnAccept(); AutoLoginTokenDone=1; AutoLoginTokenStage=11; return "
        "end "

        // Method C: direct C-exposed Lua submit
        "if type(AcceptToken_AccountLogin) == 'function' then "
        "  AcceptToken_AccountLogin(code); AutoLoginTokenDone=1; AutoLoginTokenStage=12; return "
        "end "
        "if type(AcceptToken) == 'function' then "
        "  AcceptToken(code); AutoLoginTokenDone=1; AutoLoginTokenStage=13; return "
        "end "

        // Method D: try common button names
        "local btnNames = {"
        "  'TokenEnterDialogOkayButton','TokenEnterDialogOkButton',"
        "  'TokenEnterDialogAcceptButton','TokenEnterDialogButton1',"
        "  'TokenEnterDialogButton','TokenOkayButton','TokenAcceptButton'} "
        "for i=1,#btnNames do "
        "  local b = _G[btnNames[i]] "
        "  if b then "
        "    if b.Click then b:Click(); AutoLoginTokenDone=1; AutoLoginTokenStage=20+i; return end "
        "    if b.GetScript then "
        "      local fn = b:GetScript('OnClick') "
        "      if fn then fn(b, 'LeftButton'); AutoLoginTokenDone=1; AutoLoginTokenStage=30+i; return end "
        "    end "
        "  end "
        "end "

        // Method E: walk dialog children and click the first Button
        "if d.GetNumChildren and d.GetChildren then "
        "  local n = d:GetNumChildren() "
        "  local kids = {d:GetChildren()} "
        "  for i=1,n do "
        "    local c = kids[i] "
        "    if c and c.GetObjectType and c:GetObjectType() == 'Button' "
        "       and c.IsVisible and c:IsVisible() and c.Click then "
        "      c:Click(); AutoLoginTokenDone=1; AutoLoginTokenStage=40+i; return "
        "    end "
        "  end "
        "end ";

    bool ran = runLuaChunk(L, script);

    // The chunk copied the code into a local straight away, so drop it from the
    // global table — otherwise a live 2FA code sits in _G for anything to read.
    lua_pushnil(L);
    lua_setglobal(L, "AutoLoginToken");
    if (!ran) return;

    lua_getglobal(L, "AutoLoginTokenDone");
    bool ok = !lua_isnil(L, -1);
    lua_pop(L, 1);
    if (ok) {
        s_tokenSubmitted = true;
        writeLog("[token] submitted");
    }
}


static void gluexml_charenum()
{
    if (s_autologinDone || s_characterIndex >= 0)
        return;

    const char* character = currentTarget();
    if (!character) return;

    LoginUI::CharVector* chars = LoginUI::GetChars();
    if (!chars || chars->size <= 0) return;

    // This retries every frame until a match turns up, so describe the list
    // only the first time round — otherwise a character name that matches
    // nothing grows autologin.log by a screenful every second.
    const bool verbose = !s_charEnumLogged;
    s_charEnumLogged = true;
    if (verbose)
        writeLog("[charenum] looking for '%s', size=%d", character, chars->size);
    for (int i = 0; i < chars->size; i++) {
        const char* actualName = chars->buf[i].data.name;
        if (verbose)
            writeLog("[charenum]   slot[%d] = '%s'", i, actualName ? actualName : "(null)");
        if (sameCharacterName(actualName, character)) {
            writeLog("[charenum] MATCH at slot %d", i);
            s_characterIndex = i;
            return;
        }
    }
    if (verbose)
        writeLog("[charenum] no match for '%s'", character);
}


// ── character list export ──────────────────────────────────────────────────
// Each time the server sends the character list, write it next to Wow.exe so
// the manager can fill in an account's characters by itself — the user only
// has to enter the login once. Names, level, class, race: nothing secret.

static void exportCharacterList()
{
    const char* login = getParam("login");
    if (!login || !*login) return;          // not launched by the manager

    LoginUI::CharVector* chars = LoginUI::GetChars();
    if (!chars || chars->size < 0 || chars->size > 64 || !chars->buf) return;

    const char* realm = "";
    if (Console::CVar* cv = Console::FindCVar("realmName"); cv && cv->vStr)
        realm = cv->vStr;

    std::vector<CharListJson::Row> rows;
    rows.reserve(chars->size);
    for (int i = 0; i < chars->size; i++) {
        const LoginUI::CharData& d = chars->buf[i].data;
        CharListJson::Row r;
        // never read past the fixed-size name field
        r.name.assign(d.name, strnlen(d.name, sizeof(d.name)));
        r.level = (unsigned char)d.level;
        r.cls = (unsigned char)d.class_;
        r.race = (unsigned char)d.race;
        r.gender = (unsigned char)d.gender;
        rows.push_back(r);
    }

    FILETIME ft;
    GetSystemTimeAsFileTime(&ft);
    ULARGE_INTEGER ull;
    ull.LowPart = ft.dwLowDateTime;
    ull.HighPart = ft.dwHighDateTime;
    unsigned long long unixSec =
        (ull.QuadPart - 116444736000000000ULL) / 10000000ULL;
    std::string json = CharListJson::build(login, realm, unixSec, rows);

    std::string dir;
    {
        char exe[MAX_PATH] = {0};
        DWORD n = GetModuleFileNameA(NULL, exe, MAX_PATH);
        if (!n || n >= MAX_PATH) return;
        dir.assign(exe, n);
        size_t slash = dir.find_last_of('\\');
        if (slash == std::string::npos) return;
        dir.resize(slash + 1);
        dir += "WowManagerData";
    }
    CreateDirectoryA(dir.c_str(), NULL);

    char hash[16];
    std::snprintf(hash, sizeof(hash), "%08x", CharListJson::fnv1a(realm));
    std::string path = dir + "\\" + CharListJson::fileSafe(login) + "__"
                     + hash + ".json";

    // Write-then-rename, so the manager never reads half a file.
    std::string tmp = path + ".tmp";
    FILE* f = NULL;
    if (fopen_s(&f, tmp.c_str(), "wb") != 0 || !f) return;
    fwrite(json.data(), 1, json.size(), f);
    fclose(f);
    if (MoveFileExA(tmp.c_str(), path.c_str(), MOVEFILE_REPLACE_EXISTING))
        writeLog("[export] %d characters for this account", (int)rows.size());
    else
        DeleteFileA(tmp.c_str());
}


// The client just handed us a (possibly different) character list.
static void gluexml_charlist_arrived()
{
    s_charEnumLogged = false;
    s_listSinceSwitch = true;
    exportCharacterList();
    gluexml_charenum();
}


// Runs on every FrameScript OnUpdate — in the glue AND in the world, so the
// very first thing it does is make sure it stays out of the game's way.
// WowManagerSwitchCharacter("Name") — called by the WowManager addon just
// before Logout(). Logging out drops the client back to the glue screen while
// the account session stays alive, so we can pick the next character straight
// away instead of making the launcher restart the whole client. Passing "" (or
// nothing useful) cancels a request the player backed out of.
static int lua_WowManagerSwitchCharacter(lua_State* L)
{
    const char* name = luaL_checkstring(L, 1);
    s_pendingSwitch = name ? name : "";
    s_pendingTick = GetTickCount();
    s_listSinceSwitch = false;
    writeLog("[switch] requested '%s'", s_pendingSwitch.c_str());
    return 0;
}


static int lua_openwowmanagerlib(lua_State* L)
{
    lua_pushcfunction(L, lua_WowManagerSwitchCharacter);
    lua_setglobal(L, "WowManagerSwitchCharacter");
    return 0;
}


static void gluexml_character_onupdate()
{
    lua_State* L0 = GetLuaState();
    const DWORD now0 = GetTickCount();

    if (s_autologinDone) {
        // Normally we stay retired for the rest of the process. The exception
        // is an in-client character switch: the addon named a target and then
        // logged out, so the glue screen belongs to us again.
        //
        // "Back on the glue" is judged by the glue's own Lua global rather than
        // the client's in-world byte, which is not guaranteed to clear on
        // logout the way it is set on login.
        if (s_pendingSwitch.empty() || !glueAlive(L0))
            return;
        if (now0 - s_pendingTick > kSwitchTtlMs) {
            writeLog("[switch] request for '%s' expired", s_pendingSwitch.c_str());
            s_pendingSwitch.clear();
            return;
        }
        s_targetCharacter = s_pendingSwitch;
        s_targetInit      = true;
        s_pendingSwitch.clear();
        s_characterIndex  = -1;
        s_selectIssued    = false;
        s_enterTries      = 0;
        s_charEnumLogged  = false;
        s_autologinDone   = false;
        s_switchMode      = true;
        s_rearmTick       = now0;
        writeLog("[switch] re-arming for '%s'", s_targetCharacter.c_str());
    }

    // Reaching the world retires the whole machine for the rest of the process:
    // logging out back to character select later is the player's business, not
    // ours, and re-entering from here would fight them.
    if (IsInWorld() && !glueAlive(L0)) {
        s_autologinDone = true;
        s_switchMode = false;
        writeLog("[onupdate] world reached, autologin disarmed");
        return;
    }

    // 2FA dialog can pop up at any point before the character list, so keep
    // trying while we're on the glue. Cheap no-op once submitted.
    tryTokenSubmit();

    if (s_characterIndex < 0) {
        // Right after a logout the client still holds the list we left, and a
        // slot picked from it before the screen is ready gets ignored. Wait for
        // the server's fresh list (or give up waiting after a few seconds).
        if (s_switchMode && !s_listSinceSwitch
                && now0 - s_rearmTick < kFreshListWaitMs)
            return;
        gluexml_charenum();
        return;
    }

    const int idx = s_characterIndex;
    const DWORD now = GetTickCount();

    if (!s_selectIssued) {
        s_selectIssued = true;
        s_selectTick = now;
        writeLog("[onupdate] SelectCharacter(%d)", idx + 1);
        if (lua_State* L = GetLuaState()) {
            *(int*)0x00AC436C = idx;
            callLuaSelect(L, idx + 1);
        }
        return;
    }

    if (s_enterTries == 0) {
        if (now - s_selectTick < kSelectSettleMs)
            return;
    } else {
        // A retry is only ever safe when the character-select screen is STILL
        // up — if the enter went through we are mid-loading-screen and a second
        // EnterWorld would get the session dropped.
        if (s_enterTries >= kMaxEnterTries) return;
        if (now - s_enterTick < kEnterRetryMs) return;
        if (!atCharacterSelect(GetLuaState())) return;
        writeLog("[onupdate] still on character select %u ms after attempt %d",
                 now - s_enterTick, s_enterTries);
    }

    s_enterTries++;
    s_enterTick = now;

    lua_State* L = GetLuaState();
    if (s_enterTries == 1 && L) {
        writeLog("[onupdate] EnterWorld() for slot %d", idx);
        *(int*)0x00AC436C = idx;
        callLuaFunction0(L, "EnterWorld");
        return;
    }

    // GlueXML didn't take it — go straight at the client function.
    writeLog("[onupdate] attempt %d: C-level EnterWorld(%d)", s_enterTries, idx);
    LoginUI::EnterWorld(idx);
}


static void gluexml_postload()
{
    static bool s_once = false;
    if (s_once) return;
    s_once = true;

    const char* realmList = getParam("realmlist");
    if (Console::CVar* cvar = Console::FindCVar("realmList"); cvar && realmList) {
        Console::SetCVarValue(cvar, realmList, 1, 0, 0, 1);
        writeLog("[postload] realmList = %s", realmList);
    }

    const char* realmname = getParam("realmname");
    if (Console::CVar* cvar = Console::FindCVar("realmName"); cvar && realmname) {
        Console::SetCVarValue(cvar, realmname, 1, 0, 0, 1);
        writeLog("[postload] realmName = %s", realmname);
    }

    // Per-launch graphics / sound preset from the manager: every
    // "cvar_<Name>" entry in autologin.json is applied before the world loads
    // (lighter settings for a background window, sound off for a second
    // client). Unknown names are skipped, so a typo can't break the launch.
    loadJsonParams();
    for (const auto& [key, value] : s_jsonParams) {
        if (key.rfind("cvar_", 0) != 0 || value.empty())
            continue;
        const char* name = key.c_str() + 5;
        if (Console::CVar* cv = Console::FindCVar(name)) {
            Console::SetCVarValue(cv, value.c_str(), 1, 0, 0, 1);
            writeLog("[preset] %s = %s", name, value.c_str());
        } else {
            writeLog("[preset] unknown cvar '%s' skipped", name);
        }
    }

    const char* login = getParam("login");
    const char* password = getParam("password");
    if (login && password) {
        writeLog("[postload] NetClient::Login(%s, ***)", login);
        NetClient::Login(login, password);
    }
}


// ── anti-AFK ────────────────────────────────────────────────────────────────
// The client keeps the time of the last mouse / keyboard event at 0xB499A4
// and compares it with its own clock (0x86AE20) in the per-frame world update
// at 0x52B24C: 5 minutes idle sets the AFK flag, 30 minutes logs the character
// out. Verified against Wow.exe 3.3.5a build 12340. Refreshing that timestamp
// from the same clock keeps both timers from ever firing. Server-side checks
// (for example battleground inactivity) are not affected.
static DWORD* const kLastHardwareAction = (DWORD*)0x00B499A4;
static DWORD (*const OsGetAsyncTimeMs)() = (DWORD(*)())0x0086AE20;
static const DWORD kAntiAfkEveryMs = 20000;

static void antiafk_onupdate()
{
    static int enabled = -1;
    if (enabled < 0) {
        const char* v = getParam("antiafk");
        enabled = (v && strcmp(v, "1") == 0) ? 1 : 0;
        if (enabled)
            writeLog("[antiafk] enabled");
    }
    if (!enabled || !IsInWorld())
        return;
    static DWORD s_lastTick = 0;
    DWORD now = GetTickCount();
    if (s_lastTick && now - s_lastTick < kAntiAfkEveryMs)
        return;
    s_lastTick = now;
    *kLastHardwareAction = OsGetAsyncTimeMs();
}


void CommandLine::initialize()
{
    int argc = 0;
    wchar_t** argv = CommandLineToArgvW(GetCommandLineW(), &argc);
    for (int i = 0; i < argc; i++)
        s_commandLine.emplace_back(u16tou8(argv[i]));

    writeLog("=== AwesomeWotlk autologin ===");
    // Log the shape of the command line, never its values — a -password or
    // -totp_secret argument would otherwise end up in a plaintext file that
    // lives next to Wow.exe.
    for (int i = 0; i < argc; i++) {
        const std::string& arg = s_commandLine[i];
        bool looksLikeFlag = !arg.empty() && (arg[0] == '-' || arg[0] == '/');
        writeLog("[init] arg[%d] = %s", i,
                 (i == 0 || looksLikeFlag) ? arg.c_str() : "<value>");
    }

    Hooks::FrameXML::registerLuaLib(lua_openwowmanagerlib);
    Hooks::GlueXML::registerCharEnum(gluexml_charlist_arrived);
    Hooks::GlueXML::registerPostLoad(gluexml_postload);
    Hooks::FrameScript::registerOnUpdate(gluexml_character_onupdate);
    Hooks::FrameScript::registerOnUpdate(antiafk_onupdate);
}
