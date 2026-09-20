# -*- coding: utf-8 -*-
"""Run the addon's real Lua under a mocked WoW API: the chat group-finder
parser and the cross-character friends / ignore sync.

Needs `pip install lupa`; skipped without it.
"""
import io, sys

try:
    import lupa
except ImportError:
    print("SKIP: lupa is not installed (pip install lupa)")
    raise SystemExit(0)

ok = []


def check(name, cond):
    ok.append((name, bool(cond)))
    print(("PASS " if cond else "FAIL ") + name)


MOCK = r'''
local function newFrame()
    local f = { scripts = {}, shown = true, events = {} }
    setmetatable(f, { __index = function(t, k)
        -- like a real frame: methods (CamelCase) exist, other fields are nil
        if type(k) ~= "string" or not k:match("^[A-Z]") then return nil end
        return function(self, ...)
            if k == "SetScript" then local name, fn = ...; t.scripts[name] = fn
            elseif k == "GetScript" then return t.scripts[(...)]
            elseif k == "Show" then t.shown = true
            elseif k == "Hide" then t.shown = false
            elseif k == "IsShown" then return t.shown
            elseif k == "RegisterEvent" then t.events[(...)] = true
            elseif k == "CreateFontString" or k == "CreateTexture" then
                return newFrame()
            elseif k == "GetFontString" then return newFrame()
            elseif k == "GetStringWidth" or k == "GetWidth" then return 40
            end
        end
    end })
    return f
end
FRAMES = {}
function CreateFrame(kind, name) local f = newFrame(); FRAMES[#FRAMES + 1] = f
    if name then _G[name] = f end; return f end
UIParent, Minimap, GameTooltip = newFrame(), newFrame(), newFrame()
DEFAULT_CHAT_FRAME = newFrame()
CHAT = {}
DEFAULT_CHAT_FRAME.AddMessage = function(_, m) CHAT[#CHAT + 1] = m end
UISpecialFrames, SlashCmdList = {}, {}
tinsert = table.insert
NOW = 1000000
function time() return NOW end
PLAYER, REALM, FACTION = "Alpha", "Realm", "Horde"
function UnitName() return PLAYER end
function GetRealmName() return REALM end
function UnitFactionGroup() return FACTION end
function UnitLevel() return 80 end
function UnitClass() return "Паладин", "PALADIN" end

-- one server-side friends list per character
LISTS = {}
local function mine() LISTS[PLAYER] = LISTS[PLAYER] or { friends = {}, ignore = {} }
    return LISTS[PLAYER] end
REFUSE = {}          -- names the "server" won't accept
function GetNumFriends() return #mine().friends end
function GetFriendInfo(i) local e = mine().friends[i]
    return e.name, 80, "Mage", "Dalaran", true, "", e.note end
function AddFriend(n) if not REFUSE[n] then
    table.insert(mine().friends, { name = n }) end end
function RemoveFriend(n) local l = mine().friends
    for i = #l, 1, -1 do if l[i].name == n then table.remove(l, i) end end end
function SetFriendNotes(n, note) for _, e in ipairs(mine().friends) do
    if e.name == n then e.note = note end end end
function GetNumIgnores() return #mine().ignore end
function GetIgnoreName(i) return mine().ignore[i] end
function AddIgnore(n) table.insert(mine().ignore, n) end
function DelIgnore(n) local l = mine().ignore
    for i = #l, 1, -1 do if l[i] == n then table.remove(l, i) end end end
function GetItemInfo() return nil end
QUIT, LOGGED_OUT, SWITCHED = false, false, nil
function Quit() QUIT = true end
function Logout() LOGGED_OUT = true end
function WowManagerSwitchCharacter(n) SWITCHED = n end
function GetInventoryItemLink() return nil end
RAID_CLASS_COLORS = { MAGE = { r = 0.4, g = 0.8, b = 1 } }
'''

src = io.open("addon/WowManager/Core.lua", encoding="utf-8").read()
EXPORT = '''
return { parseLfg = parseLfg, lowerUtf8 = lowerUtf8, parseGS = parseGS,
         socialPut = socialPut, socialTake = socialTake,
         socialShared = function(kind)
             local out = {}
             for i, e in ipairs(socialShared(kind)) do out[i] = e end
             return out
         end,
         computeGearScore = computeGearScore,
         syncList = syncList, socialTicker = socialTicker,
         socialQueue = function() return socialQueue end,
         onLfgChat = onLfgChat, lfgEntries = lfgEntries,
         socialRecheck = socialRecheck, harvestTimer = harvestTimer,
         events = f }
'''

L = lupa.LuaRuntime(unpack_returned_tuples=True)
L.execute(MOCK)
L.execute('WowManagerDB = {}; WowManagerCharDB = {}; WowManagerConfig = '
          '{ syncFriends = true, lfg = true, characters = {} }')
mod = L.execute(src + EXPORT)
lua = L.globals()

# ── Cyrillic lower-casing ──────────────────────────────────────────────────
check("lowerUtf8 folds Cyrillic", mod.lowerUtf8("ЦЛК25 ГЕР Ёж") == "цлк25 гер ёж")
check("lowerUtf8 keeps ASCII", mod.lowerUtf8("ICC HeAl") == "icc heal")


def ad(msg):
    r = mod.parseLfg(msg)
    if r is None:
        return None
    roles = "".join(k for k in "THD" if r.roles[k])
    return (r.raid, r.size, bool(r.heroic), roles, r.gs, bool(r.seeker))


check("ICC 25 heroic, healers and ranged, GS 5.8k",
      ad("ЦЛК25 гер нужны 2 хила и рдд гс 5.8к+") == ("ICC", 25, True, "HD", 5800, False))
check("ToC 10 tank, GS 5500+",
      ad("ИК 10 нужен танк 5500+") == ("TOC", 10, False, "T", 5500, False))
check("English LFG ad is marked as a seeker",
      ad("LFG ICC25 heal 5.6k gs") == ("ICC", 25, False, "H", 5600, True))
check("GS given in hundreds after the marker", ad("ОС 10 дд гс 52")[4] == 5200)
check("RS heroic in English", ad("RS25 HC need tank")[0:3] == ("RS", 25, True))
check("a trade message is not a raid", ad("продам шлем недорого") is None)
check("'ик' inside a word doesn't count", ad("никто не идет") is None)
check("raid number alone isn't a GS", ad("ЦЛК 25 нужны все")[4] is None)
check("a four-digit number without a marker isn't a GS",
      ad("ульда 25 сбор 2019 года")[4] is None)
# real ads people posted, where the old parser found nothing
check("'от 5700к' is a gear score",
      ad("В ЦЛК 25(об) нид КОТ или Хпал от 5700к БОЕ-А ДИС МФ 24/25")[4] == 5700)
check("'от 6.2' means 6200",
      ad("-----Цлк 25хм нужны Рпал/Ппал Дц/.Ршам! (Дц/Ршам) от 6.2 4т10.2")[4]
      == 6200)
check("tier gear is not a gear score", mod.parseGS("цлк 25 4т10.2 нужны дд")
      is None)
check("free spots are not a gear score", mod.parseGS("ик 10 идем 8/10") is None)
check("a plain '6' is not a gear score", mod.parseGS("ульда 25 идем 6 боссов")
      is None)
check("'5,9+' is read with a comma", mod.parseGS("цлк 25 дд 5,9+") == 5900)

# ── GearScore: the same numbers the GearScore addon shows ─────────────────
L.execute("""
ITEMS, EQUIP = {}, {}
function GetItemInfo(link)
    local it = ITEMS[link]
    if not it then return nil end
    return link, link, it.rarity, it.ilvl, nil, nil, nil, nil, it.loc
end
function GetInventoryItemLink(_, slot) return EQUIP[slot] end
function equip(slot, rarity, ilvl, loc)
    local link = "item" .. slot
    ITEMS[link] = { rarity = rarity, ilvl = ilvl, loc = loc }
    EQUIP[slot] = link
end
function clearGear() EQUIP = {}; ITEMS = {} end
""")
gear = lua.equip
clear = lua.clearGear
gs = mod.computeGearScore

clear()
check("no gear scores nothing", gs() == 0)
clear(); gear(1, 4, 264, "INVTYPE_HEAD")
check("an epic 264 head scores 494 like GearScore does", gs() == 494)
clear(); gear(1, 3, 200, "INVTYPE_HEAD")
check("a blue item uses its own constants", gs() == 271)
clear(); gear(16, 4, 264, "INVTYPE_2HWEAPON")
check("a two-hander counts double", gs() == 988)
clear(); gear(16, 4, 264, "INVTYPE_2HWEAPON"); gear(17, 4, 264, "INVTYPE_WEAPON")
check("Titan's Grip halves both weapons", gs() == 741)
clear(); gear(13, 4, 264, "INVTYPE_TRINKET")
check("a trinket counts by its slot weight", gs() == 278)
clear(); gear(4, 2, 264, "INVTYPE_BODY")
check("the shirt is skipped", gs() == 0)
clear(); gear(19, 4, 264, "INVTYPE_HEAD")
check("the tabard is skipped", gs() == 0)
L.execute('function UnitClass() return "Охотник", "HUNTER" end')
clear(); gear(18, 4, 264, "INVTYPE_RANGED")
check("a hunter's bow is his real weapon", gs() == 830)
L.execute('function UnitClass() return "Паладин", "PALADIN" end')
clear(); gear(18, 4, 264, "INVTYPE_RANGED")
check("for everyone else the ranged slot barely counts", gs() == 156)
clear()

# chat feed keeps one ad per author, newest wins
mod.onLfgChat("ЦЛК25 нужен хил гс 5.5к", "Leader", None)
mod.onLfgChat("ЦЛК25 нужен хил гс 5.6к", "Leader", None)
mod.onLfgChat("хорошего дня", "Other", None)
entries = list(mod.lfgEntries.keys())
check("one ad per author, chatter ignored", entries == ["Leader"])
check("the author's newer ad replaces the old one",
      mod.lfgEntries["Leader"].gs == 5600)


# ── friends sync across characters ─────────────────────────────────────────
def drain():
    tick = mod.socialTicker.scripts["OnUpdate"]
    for _ in range(200):
        if not mod.socialTicker.shown:
            break
        tick(mod.socialTicker, 1.0)


char_db = {}


def as_char(name):
    lua.PLAYER = name
    if name not in char_db:
        char_db[name] = L.eval("{}")
    lua.WowManagerCharDB = char_db[name]


def recheck():
    f = mod.socialRecheck
    if f.shown:
        f.scripts["OnUpdate"](f, 60.0)


def friends_of(name):
    lst = lua.LISTS[name]
    return sorted(e.name for e in lst.friends.values()) if lst else []


def login_sync(name):
    as_char(name)
    mod.syncList("friends")
    drain()
    mod.syncList("friends")     # the game fires an update after the adds


# Alpha already has two friends
as_char("Alpha")
L.execute('LISTS.Alpha = { friends = { {name="Bob", note="танк"}, {name="Carl"} }, ignore = {"Spammer"} }')
login_sync("Alpha")
as_char("Alpha"); mod.syncList("ignore"); drain()

# Beta logs in with an empty list and gets both, plus the ignore entry
login_sync("Beta")
as_char("Beta"); mod.syncList("ignore"); drain()
check("second character receives the shared friends",
      friends_of("Beta") == ["Bob", "Carl"])
check("friend notes travel too",
      any(e.note == "танк" for e in lua.LISTS["Beta"].friends.values()))
check("ignore list is shared", list(lua.LISTS["Beta"].ignore.values()) == ["Spammer"])
check("a summary line is printed", any("синхронизированы" in m for m in lua.CHAT.values()))

# Beta adds Dana -> Alpha gets her on next login
as_char("Beta"); lua.AddFriend("Dana"); mod.syncList("friends")
lua.NOW = lua.NOW + 60
login_sync("Alpha")
check("a friend added on one character reaches the others",
      friends_of("Alpha") == ["Bob", "Carl", "Dana"])

# Alpha removes Carl -> Beta drops Carl on next login
lua.NOW = lua.NOW + 60
as_char("Alpha"); lua.RemoveFriend("Carl"); mod.syncList("friends")
lua.NOW = lua.NOW + 10
as_char("Alpha"); recheck()                # the automatic re-check fires
lua.NOW = lua.NOW + 60
login_sync("Beta")
check("a removal on one character reaches the others",
      friends_of("Beta") == ["Bob", "Dana"])
check("...and the removed friend is not added back to Alpha",
      friends_of("Alpha") == ["Bob", "Dana"])

# Beta deliberately re-adds Carl later -> that wins over the old removal
lua.NOW = lua.NOW + 60
as_char("Beta"); lua.AddFriend("Carl"); mod.syncList("friends")
lua.NOW = lua.NOW + 60
login_sync("Alpha")
check("re-adding after a removal brings the friend back everywhere",
      "Carl" in friends_of("Alpha"))

# right after login the list comes back empty: nothing may be wiped
before_alpha = friends_of("Alpha")
as_char("Alpha")
saved = lua.LISTS["Alpha"].friends
lua.LISTS["Alpha"].friends = L.eval("{}")
mod.syncList("friends")                    # the empty glitch update
check("an empty update queues nothing", not mod.socialTicker.shown)
lua.NOW = lua.NOW + 2
lua.LISTS["Alpha"].friends = saved         # the real list arrives
mod.syncList("friends"); drain()
lua.NOW = lua.NOW + 30
as_char("Alpha"); recheck()
login_sync("Beta")
check("an empty list right after login wipes nothing",
      friends_of("Alpha") == before_alpha and "Bob" in friends_of("Beta"))

# a friend the player really removes is not re-added while pending
lua.NOW = lua.NOW + 60
as_char("Alpha"); lua.RemoveFriend("Bob"); mod.syncList("friends"); drain()
check("a pending removal is not undone by the same character",
      "Bob" not in friends_of("Alpha"))

# a name the server refuses is tried twice, then left alone
as_char("Beta"); lua.AddFriend("Ghost"); mod.syncList("friends")  # shared now
lua.REFUSE["Ghost"] = True                 # ...and then the character is gone
attempts = 0
real_add = lua.AddFriend


def counting_add(n):
    global attempts
    if n == "Ghost":
        attempts += 1
    real_add(n)


lua.AddFriend = counting_add
for _ in range(5):
    lua.NOW = lua.NOW + 60
    login_sync("Alpha")
check("a refused name is tried at most twice", attempts == 2)

# ── the lists edited in game ──────────────────────────────────────────────
# The editor window writes straight into the shared list, and the sync then
# carries the change to every character.
lua.NOW = lua.NOW + 60
as_char("Alpha")
mod.socialPut("friends", "  Гость  ")
drain()
check("a name added in the editor is put on this character",
      "Гость" in friends_of("Alpha"))
check("...with the spaces trimmed off",
      any(e.name == "Гость" for e in lua.LISTS["Alpha"].friends.values()))
lua.NOW = lua.NOW + 60
login_sync("Beta")
check("the added name reaches the other characters",
      "Гость" in friends_of("Beta"))

names = [e.name for e in mod.socialShared("friends").values()]
check("the editor lists what the sync works from", "Гость" in names)

as_char("Alpha")
entry = next(e for e in mod.socialShared("friends").values()
             if e.name == "Гость")
mod.socialTake("friends", entry)
drain()
check("removing in the editor takes the name off this character",
      "Гость" not in friends_of("Alpha"))
lua.NOW = lua.NOW + 60
login_sync("Beta")
check("...and off the others", "Гость" not in friends_of("Beta"))

# a character can sit the sync out
lua.NOW = lua.NOW + 60
as_char("Beta")
lua.WowManagerCharDB.socialOff = True
before = friends_of("Beta")
mod.socialPut("friends", "Отдельный")
drain()
check("a character with the sync off is left alone",
      friends_of("Beta") == before)
lua.NOW = lua.NOW + 60
login_sync("Alpha")
check("...while the others still get the name",
      "Отдельный" in friends_of("Alpha"))
as_char("Beta")
lua.WowManagerCharDB.socialOff = None
login_sync("Beta")
check("switching the sync back on catches the character up",
      "Отдельный" in friends_of("Beta"))
as_char("Alpha")
mod.socialTake("friends", next(e for e in mod.socialShared("friends").values()
                               if e.name == "Отдельный"))
drain()

# ── harvest mode walks the account's characters ────────────────────────────
def enter_world():
    mod.events.scripts["OnEvent"](mod.events, "PLAYER_ENTERING_WORLD")


def harvest_tick():
    t = mod.harvestTimer
    if t.shown:
        t.scripts["OnUpdate"](t, 60.0)


lua.WowManagerConfig = L.eval(
    '{ syncFriends = false, lfg = false, harvest = true, harvestWait = 12,'
    '  harvestChars = { "Alpha", "Beta", "Gamma" } }')

# Switching characters reloads the addon, so each one is a fresh chunk.
def session(name):
    global mod
    as_char(name)
    lua.SWITCHED, lua.LOGGED_OUT, lua.QUIT = None, False, False
    mod = L.execute(src + EXPORT)
    return mod


hm = session("Beta")
enter_world()
check("harvest waits before collecting", hm.harvestTimer.shown)
check("nothing happens before the wait is over", lua.SWITCHED is None)
harvest_tick()
check("harvest moves on to the next character", lua.SWITCHED == "Gamma")
check("...by logging out, not restarting", lua.LOGGED_OUT and not lua.QUIT)
check("data was collected for this character",
      lua.WowManagerDB["Realm.Beta"] is not None)

hm = session("Gamma")
enter_world()
harvest_tick()
check("the last character quits the game", lua.QUIT and lua.SWITCHED is None)

# a character that isn't on the list starts the walk from the top
hm = session("Delta")
enter_world()
harvest_tick()
check("an unlisted character starts at the top", lua.SWITCHED == "Alpha")

# and with harvest off nothing happens at all
lua.WowManagerConfig = L.eval('{ syncFriends = false, lfg = false }')
hm = session("Alpha")
enter_world()
check("harvest stays off unless the manager asks",
      not hm.harvestTimer.shown and not lua.QUIT)

print()
bad = [n for n, v in ok if not v]
print("%d/%d passed" % (len(ok) - len(bad), len(ok)))
sys.exit(1 if bad else 0)
