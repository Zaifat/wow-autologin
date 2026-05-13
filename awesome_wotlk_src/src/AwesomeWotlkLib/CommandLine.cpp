#include "CommandLine.h"
#include "Hooks.h"
#include "GameClient.h"
#include "Utils.h"
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
static volatile LONG s_characterIndex = -1;
static volatile LONG s_characterEntered = 0;
static volatile LONG s_charSelectedFrames = 0;
static volatile LONG s_tokenSubmitted = 0;


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


static bool sameCharacterName(const char* actual, const char* expected)
{
    if (!(actual && expected && *actual && *expected))
        return false;
    return strcmp(actual, expected) == 0 || _stricmp(actual, expected) == 0;
}


static const char* kSelectFuncs[] = {
    "CharacterSelect_SelectCharacter",
    "SelectCharacter",
    NULL,
};


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


static std::string computeTotp(const std::string& base32Secret)
{
    std::vector<uint8_t> key;
    if (!base32Decode(base32Secret.c_str(), key)) return "";

    // Unix time in seconds, 30s window
    FILETIME ft;
    GetSystemTimeAsFileTime(&ft);
    ULARGE_INTEGER ull;
    ull.LowPart = ft.dwLowDateTime;
    ull.HighPart = ft.dwHighDateTime;
    // FILETIME = 100-ns intervals since 1601; Unix = seconds since 1970
    uint64_t unixSec = (ull.QuadPart - 116444736000000000ULL) / 10000000ULL;
    uint64_t counter = unixSec / 30;

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
        std::string code = computeTotp(secret);
        if (!code.empty()) {
            writeLog("[totp] computed fresh code=%s", code.c_str());
            return code;
        }
        writeLog("[totp] failed to compute from secret");
    }
    // Legacy fallback: static pre-computed token
    const char* tok = getParam("token");
    if (tok && *tok) return std::string(tok);
    return "";
}


static void tryTokenSubmit()
{
    if (InterlockedCompareExchange(&s_tokenSubmitted, 0, 0)) return;

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

    lua_getglobal(L, "loadstring");
    if (!lua_isfunction(L, -1)) { lua_pop(L, 1); return; }
    lua_pushstring(L, script);
    if (lua_pcall(L, 1, 1, 0) != 0) { lua_pop(L, 1); return; }
    if (!lua_isfunction(L, -1)) { lua_pop(L, 1); return; }
    if (lua_pcall(L, 0, 0, 0) != 0) { lua_pop(L, 1); return; }

    lua_getglobal(L, "AutoLoginTokenDone");
    bool ok = (lua_type(L, -1) != 0); // 0 == LUA_TNIL
    lua_pop(L, 1);
    if (ok) {
        InterlockedExchange(&s_tokenSubmitted, 1);
        writeLog("[token] submitted");
    }
}


static void gluexml_charenum()
{
    if (InterlockedCompareExchange(&s_characterEntered, 0, 0))
        return;
    if (InterlockedCompareExchange(&s_characterIndex, 0, 0) >= 0)
        return;

    const char* character = getParam("character");
    if (!character) return;

    LoginUI::CharVector* chars = LoginUI::GetChars();
    if (!chars || chars->size <= 0) return;

    writeLog("[charenum] looking for '%s', size=%d", character, chars->size);
    for (int i = 0; i < chars->size; i++) {
        const char* actualName = chars->buf[i].data.name;
        writeLog("[charenum]   slot[%d] = '%s'", i, actualName ? actualName : "(null)");
        if (sameCharacterName(actualName, character)) {
            writeLog("[charenum] MATCH at slot %d", i);
            InterlockedExchange(&s_charSelectedFrames, 0);
            InterlockedExchange(&s_characterIndex, i);
            return;
        }
    }
    writeLog("[charenum] no match for '%s'", character);
}


static void gluexml_character_onupdate()
{
    // Try to submit the 2FA token if a -token arg was provided and the
    // authenticator dialog is currently visible. Cheap no-op once submitted.
    tryTokenSubmit();

    if (InterlockedCompareExchange(&s_characterEntered, 0, 0))
        return;

    int idx = InterlockedCompareExchange(&s_characterIndex, 0, 0);
    if (idx < 0) {
        gluexml_charenum();
        return;
    }

    LONG frames = InterlockedIncrement(&s_charSelectedFrames);

    if (frames == 1) {
        writeLog("[onupdate] frame=1: SelectCharacter(%d)", idx + 1);
        if (lua_State* L = GetLuaState()) {
            *(int*)0x00AC436C = idx;
            callLuaSelect(L, idx + 1);
        }
    }

    if (frames == 30) {
        writeLog("[onupdate] frame=30: EnterWorld() for slot %d", idx);
        if (lua_State* L = GetLuaState()) {
            *(int*)0x00AC436C = idx;
            if (callLuaFunction0(L, "EnterWorld"))
                InterlockedExchange(&s_characterEntered, 1);
        }
    }

    if (frames == 90 && !InterlockedCompareExchange(&s_characterEntered, 0, 0)) {
        writeLog("[onupdate] frame=90: C-level fallback EnterWorld(%d)", idx);
        *(int*)0x00AC436C = idx;
        ((void(*)())0x004D9BD0)();
        InterlockedExchange(&s_characterEntered, 1);
    }
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

    const char* login = getParam("login");
    const char* password = getParam("password");
    if (login && password) {
        writeLog("[postload] NetClient::Login(%s, ***)", login);
        NetClient::Login(login, password);
    }
}


void CommandLine::initialize()
{
    int argc = 0;
    wchar_t** argv = CommandLineToArgvW(GetCommandLineW(), &argc);
    for (int i = 0; i < argc; i++)
        s_commandLine.emplace_back(u16tou8(argv[i]));

    writeLog("=== AwesomeWotlk autologin ===");
    for (int i = 0; i < argc; i++)
        writeLog("[init] arg[%d] = '%s'", i, s_commandLine[i].c_str());

    Hooks::GlueXML::registerCharEnum(gluexml_charenum);
    Hooks::GlueXML::registerPostLoad(gluexml_postload);
    Hooks::FrameScript::registerOnUpdate(gluexml_character_onupdate);
}
