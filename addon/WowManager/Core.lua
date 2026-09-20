-- WoW Manager addon (3.3.5a)
-- 1) Collects all reachable character data into account-wide SavedVariables
--    so the manager can show it in the hover card / list columns.
-- 2) Optional minimap button → relog menu built from the MANAGER's character
--    list (WowManagerConfig.characters).

WowManagerDB = WowManagerDB or {}          -- account-wide: [realm.name] = {data}
WowManagerCharDB = WowManagerCharDB or {}

local function ckey()
    return (GetRealmName() or "?") .. "." .. (UnitName("player") or "?")
end

-- Case folding that doesn't depend on the process locale. string.lower does,
-- and under some locales it rewrites the lead byte of every Cyrillic UTF-8
-- character (0xD0 -> 0xF0), silently corrupting the text. Only explicit byte
-- ranges here: ASCII A-Z, and Cyrillic А-Я / Ё.
local function foldCase(s)
    s = s:gsub("[A-Z]", function(c) return string.char(c:byte() + 32) end)
    s = s:gsub("\208([\144-\159])", function(c)
        return "\208" .. string.char(c:byte() + 32) end)
    s = s:gsub("\208([\160-\175])", function(c)
        return "\209" .. string.char(c:byte() - 32) end)
    s = s:gsub("\208\129", "\209\145")
    return s
end

-- ── GearScore (fallback if the GearScore addon isn't installed) ─────────────
local GS_QUALITY = { [0]=0.005, [1]=0.2, [2]=0.4, [3]=0.7, [4]=0.85, [5]=0.92, [6]=1, [7]=1.2 }
local GS_SLOT = {
    INVTYPE_RELIC=0.3164, INVTYPE_TRINKET=0.5625, INVTYPE_HEAD=1,
    INVTYPE_NECK=0.5625, INVTYPE_SHOULDER=0.75, INVTYPE_CHEST=1, INVTYPE_ROBE=1,
    INVTYPE_WAIST=0.75, INVTYPE_LEGS=1, INVTYPE_FEET=0.75, INVTYPE_WRIST=0.5625,
    INVTYPE_HAND=0.75, INVTYPE_FINGER=0.5625, INVTYPE_CLOAK=0.5625,
    INVTYPE_2HWEAPON=2, INVTYPE_WEAPONMAINHAND=1, INVTYPE_WEAPON=1,
    INVTYPE_WEAPONOFFHAND=1, INVTYPE_SHIELD=1, INVTYPE_HOLDABLE=1,
    INVTYPE_RANGED=0.3164, INVTYPE_THROWN=0.3164, INVTYPE_RANGEDRIGHT=0.3164,
}
local function gsItemScore(link)
    local _, _, rarity, ilvl, _, _, _, _, loc = GetItemInfo(link)
    if not ilvl then return 0 end
    local q = GS_QUALITY[rarity or 0] or 0
    local s = GS_SLOT[loc or ""] or 0
    if q == 0 or s == 0 then return 0 end
    local score
    if ilvl > 120 then
        score = ((ilvl - 91.4500) / 0.6500) * q * s * 1.8618
    else
        score = ((ilvl - 4) / 26) * q * s * 1.8618 * (ilvl / 100)
    end
    if score < 0 then score = 0 end
    return score
end
local function computeGearScore()
    local total = 0
    for slot = 1, 18 do
        if slot ~= 4 then        -- skip shirt
            local link = GetInventoryItemLink("player", slot)
            if link then total = total + gsItemScore(link) end
        end
    end
    return math.floor(total)
end

-- ── data collection ────────────────────────────────────────────────────────
-- Every optional section is wrapped in pcall: if any WoW API errors on this
-- server, the rest still collects and the record is ALWAYS saved (otherwise a
-- single failing call would abort the whole thing and leave stale gold=0 data).
local function try(fn) pcall(fn) end

local function collect()
    if not UnitName("player") then return end

    -- start from the existing record so a partial failure keeps old fields
    local d = WowManagerDB[ckey()] or {}

    try(function()
        d.name    = UnitName("player")
        d.realm   = GetRealmName()
        d.level   = UnitLevel("player")
        local _, classToken = UnitClass("player")
        d.class   = classToken
        local _, raceToken = UnitRace("player")
        d.race    = raceToken
        -- the manager picks the matching race portrait out of the client
        d.sex     = (UnitSex("player") == 3) and "female" or "male"
        d.faction = UnitFactionGroup("player")
        d.zone    = GetRealZoneText()
        d.subzone = GetSubZoneText()
        d.guild   = GetGuildInfo("player")
        d.updated = time()
    end)

    -- gold (copper). Keep a previous non-zero value if this read returns 0.
    try(function()
        local money = GetMoney()
        if money and (money > 0 or not d.gold) then d.gold = money end
    end)

    try(function()
        if UnitLevel("player") < 80 then
            d.xp = UnitXP("player"); d.xpMax = UnitXPMax("player")
        end
        d.rested = GetXPExhaustion()
    end)

    try(function()
        if GetTotalAchievementPoints then
            d.achPoints = GetTotalAchievementPoints()
        end
    end)

    try(function()
        local specName, best, tabs = nil, -1, {}
        for tab = 1, (GetNumTalentTabs() or 0) do
            local tname, _, pts = GetTalentTabInfo(tab)
            tabs[#tabs + 1] = (tname or "?") .. ":" .. (pts or 0)
            if (pts or 0) > best then best = pts or 0; specName = tname end
        end
        d.spec = specName
        d.talents = table.concat(tabs, " / ")
    end)

    try(function()
        local total, count = 0, 0
        for slot = 1, 19 do
            local link = GetInventoryItemLink("player", slot)
            if link then
                local _, _, _, ilvl = GetItemInfo(link)
                if ilvl and ilvl > 0 then total = total + ilvl; count = count + 1 end
            end
        end
        if count > 0 then d.ilvl = math.floor(total / count + 0.5) end
    end)

    try(function()
        local gs
        if type(GearScore_GetScore) == "function" then
            gs = GearScore_GetScore(d.name, "player")
        elseif type(_G.GearScore) == "number" then
            gs = _G.GearScore
        end
        if not (gs and gs > 0) then gs = computeGearScore() end   -- fallback
        if gs and gs > 0 then d.gs = math.floor(gs) end
    end)

    -- ALL currencies (expand collapsed headers first so nothing is missed)
    try(function()
        local cur = {}
        if GetCurrencyListSize then
            if ExpandCurrencyList then
                for i = GetCurrencyListSize(), 1, -1 do
                    local _, isHeader, isExp = GetCurrencyListInfo(i)
                    if isHeader and not isExp then ExpandCurrencyList(i, 1) end
                end
            end
            for i = 1, GetCurrencyListSize() do
                local cname, isHeader, _, _, _, cnt = GetCurrencyListInfo(i)
                if not isHeader and cname and cnt and cnt > 0 then
                    cur[cname] = cnt
                end
            end
        end
        if next(cur) then d.currencies = cur end
        if GetHonorCurrency then d.honor = GetHonorCurrency() end
        if GetArenaCurrency then d.arena = GetArenaCurrency() end
    end)

    try(function()
        local locks = {}
        for i = 1, ((GetNumSavedInstances and GetNumSavedInstances()) or 0) do
            local iname, _, reset, diff, locked, _, _, isRaid, maxPlayers, diffName =
                GetSavedInstanceInfo(i)
            if locked and iname and reset and reset > 0 then
                locks[#locks + 1] = {
                    name = iname, reset = reset, resetAt = time() + reset,
                    diff = diffName or tostring(diff or ""),
                    raid = isRaid and 1 or 0, max = maxPlayers or 0 }
            end
        end
        d.locks = locks
    end)

    try(function()
        local profs = {}
        for i = 1, (GetNumSkillLines() or 0) do
            local sname, isHeader, _, rank, _, _, maxRank = GetSkillLineInfo(i)
            if not isHeader and maxRank and maxRank >= 75 and rank and rank > 0 then
                profs[#profs + 1] = sname .. " " .. rank .. "/" .. maxRank
            end
        end
        d.profs = profs
    end)

    try(function()
        local free = 0
        for bag = 0, 4 do free = free + (GetContainerNumFreeSlots(bag) or 0) end
        d.bagFree = free
    end)

    -- ── "что осталось на неделе" ────────────────────────────────────────────
    -- Daily quest counter + when it rolls over. Both are plain client APIs, so
    -- this works on any 3.3.5a server and in any locale.
    try(function()
        if GetDailyQuestsCompleted then
            d.dailyDone = GetDailyQuestsCompleted()
            d.dailyMax  = MAX_DAILY_QUESTS or 25
        end
        if GetQuestResetTime then
            local left = GetQuestResetTime()
            if left and left > 0 then d.dailyResetAt = time() + left end
        end
    end)

    -- Arena games played THIS WEEK. GetArenaTeam returns the weekly counters
    -- (team and personal); the season totals sit further along the same row.
    try(function()
        local teams, mineBest = {}, 0
        for i = 1, (MAX_ARENA_TEAMS or 3) do
            local name, size, rating, teamPlayed, _, _, _, mine = GetArenaTeam(i)
            if name and size then
                mine = mine or 0
                teams[#teams + 1] = { size = size, rating = rating or 0,
                                      played = teamPlayed or 0, mine = mine }
                if mine > mineBest then mineBest = mine end
            end
        end
        if #teams > 0 then
            d.arenaTeams = teams
            d.arenaGames = mineBest
        end
    end)

    -- Quests sitting in the log already finished but never handed in.
    try(function()
        local done, total = 0, 0
        for i = 1, (GetNumQuestLogEntries() or 0) do
            local title, _, _, _, isHeader, _, isComplete = GetQuestLogTitle(i)
            if title and not isHeader then
                total = total + 1
                if isComplete and isComplete > 0 then done = done + 1 end
            end
        end
        d.questsDone, d.questsTotal = done, total
    end)

    if WowManagerCharDB.played then d.played = WowManagerCharDB.played end

    WowManagerDB[ckey()] = d     -- ALWAYS save
end

-- ── switching characters ───────────────────────────────────────────────────
-- Two paths, and the fast one is worth a lot: logging out drops the client back
-- to the character-select screen with the account session still alive, so the
-- patch DLL can walk straight into the next character. Restarting the whole
-- client is only needed when the target lives on a DIFFERENT account.
--
-- (Both paths still wait out the game's own 20s logout timer outside an inn —
-- that is a server rule, not something an addon can skip.)

local function sameAccountAs(entry)
    local mine = WowManagerConfig and WowManagerConfig.currentAccount
    return mine and mine ~= "" and entry.account and entry.account ~= ""
           and foldCase(entry.account) == foldCase(mine)
end

-- Logging out lands us on the character select of the realm we are already
-- connected to, so a character on a DIFFERENT realm is not reachable that way
-- even on the same account. An entry with no realm set is assumed to be here.
local function sameRealmAs(entry)
    local want = entry.realm
    if not want or want == "" then return true end
    local here = GetRealmName()
    return here and foldCase(here) == foldCase(want)
end

local function canSwitchInClient(entry)
    return type(WowManagerSwitchCharacter) == "function"
           and not entry.isAccount
           and entry.name and entry.name ~= ""
           and sameAccountAs(entry)
           and sameRealmAs(entry)
end

-- Slow path: record the target + quit. The manager notices once Wow.exe has
-- closed and relaunches the chosen character/account.
local function requestRelog(account, char)
    WowManagerDB.__relog = { account = account, char = char, at = time() }
    Quit()
end

-- LOGOUT_CANCEL is not only "the player moved": the game also fires it while
-- tearing the world down after a logout that DID go through (the countdown
-- popup calls CancelLogout() as it closes). Clearing the switch on the spot
-- therefore cancelled every switch. Instead, wait a few seconds: if we are
-- still in the world then, the player really cancelled; if the logout went
-- through, this Lua state is already gone and the timer never fires.
local cancelWatch = CreateFrame("Frame")
cancelWatch:Hide()
cancelWatch:SetScript("OnUpdate", function(self, elapsed)
    self.left = (self.left or 0) - elapsed
    if self.left <= 0 then
        self:Hide()
        if type(WowManagerSwitchCharacter) == "function" then
            WowManagerSwitchCharacter("")
        end
    end
end)

local function switchTo(entry)
    if canSwitchInClient(entry) then
        cancelWatch:Hide()
        WowManagerSwitchCharacter(entry.name)
        Logout()
    else
        requestRelog(entry.account, entry.name)
    end
end


-- ── alts window ─────────────────────────────────────────────────────────────
-- The whole roster inside the client: every character the manager knows about,
-- what it is carrying, and one click to go play it. Built from
-- WowManagerConfig, which the manager rewrites on every launch.

local toggleLfgWindow      -- defined with the group finder below

local ALTS_ROWS   = 13      -- visible rows
local ALTS_ROW_H  = 22
local altsFrame, altsRows, altsSelected

local function altsEntries()
    local list = (WowManagerConfig and WowManagerConfig.characters) or {}
    local chars, accs = {}, {}
    for _, c in ipairs(list) do
        if c.isAccount then accs[#accs + 1] = c else chars[#chars + 1] = c end
    end
    local out = {}
    if #chars > 0 then
        out[#out + 1] = { header = "Персонажи" }
        for _, c in ipairs(chars) do out[#out + 1] = { entry = c } end
    end
    if #accs > 0 then
        out[#out + 1] = { header = "Аккаунты" }
        for _, c in ipairs(accs) do out[#out + 1] = { entry = c } end
    end
    return out
end

local function altsColored(c, text)
    if c.color and c.color ~= "" then
        return "|cff" .. c.color .. text .. "|r"
    end
    return text
end

local function altsShowDetails()
    local c = altsSelected
    if not c then
        altsFrame.detail:SetText("|cff808080Выбери персонажа слева.|r")
        altsFrame.goBtn:Disable()
        return
    end
    local head = altsColored(c, c.name or "?")
    if c.realm and c.realm ~= "" then
        head = head .. "\n|cff808080" .. c.realm .. "|r"
    end
    local body = { head, " " }
    if c.info and #c.info > 0 then
        for _, line in ipairs(c.info) do body[#body + 1] = line end
    else
        body[#body + 1] = "|cff808080Нет данных из игры.|r"
    end
    altsFrame.detail:SetText(table.concat(body, "\n"))

    if canSwitchInClient(c) then
        altsFrame.goBtn:SetText("Зайти (без перезапуска)")
    else
        altsFrame.goBtn:SetText("Зайти (перезапуск клиента)")
    end
    altsFrame.goBtn:Enable()
end

local function altsRefresh()
    if not (altsFrame and altsFrame:IsShown()) then return end
    local items = altsEntries()
    FauxScrollFrame_Update(altsFrame.scroll, #items, ALTS_ROWS, ALTS_ROW_H)
    local offset = FauxScrollFrame_GetOffset(altsFrame.scroll)
    for i = 1, ALTS_ROWS do
        local row = altsRows[i]
        local item = items[i + offset]
        if not item then
            row:Hide()
        else
            row:Show()
            if item.header then
                row.text:SetText("|cffffd100" .. item.header .. "|r")
                row.sub:SetText("")
                row.cdata = nil
                row:Disable()
            else
                local c = item.entry
                row.text:SetText(altsColored(c, c.name or "?"))
                row.sub:SetText(c.summary or "")
                row.cdata = c
                row:Enable()
            end
            if altsSelected and row.cdata == altsSelected then
                row.sel:Show()
            else
                row.sel:Hide()
            end
        end
    end
end

local function createAltsFrame()
    if altsFrame then return altsFrame end

    local f = CreateFrame("Frame", "WowManagerAltsFrame", UIParent)
    f:SetWidth(560); f:SetHeight(400)
    f:SetPoint("CENTER")
    f:SetFrameStrata("HIGH")
    f:SetToplevel(true)
    f:SetMovable(true); f:EnableMouse(true); f:SetClampedToScreen(true)
    f:RegisterForDrag("LeftButton")
    f:SetScript("OnDragStart", function(self) self:StartMoving() end)
    f:SetScript("OnDragStop", function(self) self:StopMovingOrSizing() end)
    f:SetBackdrop({
        bgFile = "Interface\\DialogFrame\\UI-DialogBox-Background",
        edgeFile = "Interface\\DialogFrame\\UI-DialogBox-Border",
        tile = true, tileSize = 32, edgeSize = 32,
        insets = { left = 11, right = 12, top = 12, bottom = 11 } })
    f:Hide()

    local title = f:CreateFontString(nil, "OVERLAY", "GameFontNormalLarge")
    title:SetPoint("TOP", 0, -16)
    title:SetText("Менеджер персонажей")

    local close = CreateFrame("Button", nil, f, "UIPanelCloseButton")
    close:SetPoint("TOPRIGHT", -8, -8)

    -- left: the roster
    local listBg = CreateFrame("Frame", nil, f)
    listBg:SetPoint("TOPLEFT", 18, -50)
    listBg:SetWidth(280); listBg:SetHeight(ALTS_ROWS * ALTS_ROW_H + 8)
    listBg:SetBackdrop({
        bgFile = "Interface\\ChatFrame\\ChatFrameBackground",
        edgeFile = "Interface\\Tooltips\\UI-Tooltip-Border",
        tile = true, tileSize = 16, edgeSize = 12,
        insets = { left = 3, right = 3, top = 3, bottom = 3 } })
    listBg:SetBackdropColor(0, 0, 0, 0.45)

    local scroll = CreateFrame("ScrollFrame", "WowManagerAltsScroll", listBg,
                               "FauxScrollFrameTemplate")
    scroll:SetPoint("TOPLEFT", 4, -4)
    scroll:SetWidth(252); scroll:SetHeight(ALTS_ROWS * ALTS_ROW_H)
    scroll:SetScript("OnVerticalScroll", function(self, offset)
        FauxScrollFrame_OnVerticalScroll(self, offset, ALTS_ROW_H, altsRefresh)
    end)
    scroll:EnableMouseWheel(true)
    scroll:SetScript("OnMouseWheel", function(self, delta)
        local bar = _G[self:GetName() .. "ScrollBar"]
        if bar then bar:SetValue(bar:GetValue() - delta * ALTS_ROW_H) end
    end)
    f.scroll = scroll

    altsRows = {}
    for i = 1, ALTS_ROWS do
        local row = CreateFrame("Button", nil, listBg)
        row:SetWidth(250); row:SetHeight(ALTS_ROW_H)
        row:SetPoint("TOPLEFT", 5, -(4 + (i - 1) * ALTS_ROW_H))

        local sel = row:CreateTexture(nil, "BACKGROUND")
        sel:SetAllPoints()
        sel:SetTexture("Interface\\QuestFrame\\UI-QuestTitleHighlight")
        sel:SetAlpha(0.6)
        sel:Hide()
        row.sel = sel

        row:SetHighlightTexture("Interface\\QuestFrame\\UI-QuestTitleHighlight")

        local text = row:CreateFontString(nil, "OVERLAY", "GameFontNormal")
        text:SetPoint("LEFT", 4, 0)
        text:SetJustifyH("LEFT")
        row.text = text

        local sub = row:CreateFontString(nil, "OVERLAY", "GameFontDisableSmall")
        sub:SetPoint("RIGHT", -6, 0)
        sub:SetJustifyH("RIGHT")
        row.sub = sub

        row:SetScript("OnClick", function(self)
            if not self.cdata then return end
            altsSelected = self.cdata
            altsRefresh()
            altsShowDetails()
        end)
        row:SetScript("OnDoubleClick", function(self)
            if self.cdata then f:Hide(); switchTo(self.cdata) end
        end)
        altsRows[i] = row
    end

    -- right: details of whatever is selected
    local detailBg = CreateFrame("Frame", nil, f)
    detailBg:SetPoint("TOPLEFT", listBg, "TOPRIGHT", 10, 0)
    detailBg:SetWidth(232); detailBg:SetHeight(ALTS_ROWS * ALTS_ROW_H + 8)
    detailBg:SetBackdrop({
        bgFile = "Interface\\ChatFrame\\ChatFrameBackground",
        edgeFile = "Interface\\Tooltips\\UI-Tooltip-Border",
        tile = true, tileSize = 16, edgeSize = 12,
        insets = { left = 3, right = 3, top = 3, bottom = 3 } })
    detailBg:SetBackdropColor(0, 0, 0, 0.45)

    local detail = detailBg:CreateFontString(nil, "OVERLAY", "GameFontHighlightSmall")
    detail:SetPoint("TOPLEFT", 8, -8)
    detail:SetWidth(216)
    detail:SetJustifyH("LEFT"); detail:SetJustifyV("TOP")
    f.detail = detail

    local goBtn = CreateFrame("Button", nil, f, "UIPanelButtonTemplate")
    goBtn:SetWidth(240); goBtn:SetHeight(24)
    goBtn:SetPoint("BOTTOMRIGHT", -20, 20)
    goBtn:SetScript("OnClick", function()
        if altsSelected then f:Hide(); switchTo(altsSelected) end
    end)
    f.goBtn = goBtn

    local hint = f:CreateFontString(nil, "OVERLAY", "GameFontDisableSmall")
    hint:SetPoint("TOP", 0, -32)
    hint:SetText("Двойной клик по строке - зайти сразу")

    local lfgBtn = CreateFrame("Button", nil, f, "UIPanelButtonTemplate")
    lfgBtn:SetWidth(160); lfgBtn:SetHeight(24)
    lfgBtn:SetPoint("BOTTOMLEFT", 20, 20)
    lfgBtn:SetText("Поиск группы")
    lfgBtn:SetScript("OnClick", function() toggleLfgWindow() end)

    tinsert(UISpecialFrames, "WowManagerAltsFrame")   -- Esc closes it
    f:SetScript("OnShow", function() altsRefresh(); altsShowDetails() end)

    altsFrame = f
    return f
end

local function toggleAltsWindow()
    local f = createAltsFrame()
    if f:IsShown() then f:Hide() else f:Show() end
end

-- ── minimap button (overlay), draggable around the minimap edge ─────────────
local function createMinimapButton()
    if _G.WowManagerMinimapBtn then return end
    local b = CreateFrame("Button", "WowManagerMinimapBtn", Minimap)
    b:SetWidth(31); b:SetHeight(31)
    b:SetFrameStrata("MEDIUM")
    b:SetMovable(true)

    local overlay = b:CreateTexture(nil, "OVERLAY")
    overlay:SetWidth(53); overlay:SetHeight(53)
    overlay:SetTexture("Interface\\Minimap\\MiniMap-TrackingBorder")
    overlay:SetPoint("TOPLEFT")

    local icon = b:CreateTexture(nil, "BACKGROUND")
    icon:SetWidth(20); icon:SetHeight(20)
    icon:SetTexture("Interface\\Icons\\INV_Misc_GroupLooking")
    icon:SetPoint("TOPLEFT", 7, -6)

    -- position on the minimap circle by angle (radians)
    local function place(angle)
        local r = 80
        local x = math.cos(angle) * r
        local y = math.sin(angle) * r
        b:ClearAllPoints()
        b:SetPoint("CENTER", Minimap, "CENTER", x, y)
    end
    b.angle = WowManagerCharDB.minimapAngle or math.rad(200)
    place(b.angle)

    local function onDragUpdate()
        local mx, my = Minimap:GetCenter()
        local scale = Minimap:GetEffectiveScale()
        local cx, cy = GetCursorPosition()
        cx, cy = cx / scale, cy / scale
        b.angle = math.atan2(cy - my, cx - mx)
        place(b.angle)
    end
    b:RegisterForDrag("LeftButton")
    b:SetScript("OnDragStart", function(self) self:SetScript("OnUpdate", onDragUpdate) end)
    b:SetScript("OnDragStop", function(self)
        self:SetScript("OnUpdate", nil)
        WowManagerCharDB.minimapAngle = self.angle
    end)

    -- relog menu with two sections: Персонажи / Аккаунты
    local menu = CreateFrame("Frame", "WowManagerRelogMenu", UIParent)
    menu:SetFrameStrata("DIALOG")
    menu:SetBackdrop({
        bgFile = "Interface\\DialogFrame\\UI-DialogBox-Background",
        edgeFile = "Interface\\DialogFrame\\UI-DialogBox-Border",
        tile = true, tileSize = 16, edgeSize = 16,
        insets = { left = 4, right = 4, top = 4, bottom = 4 } })
    menu:Hide()
    local headers, rows = {}, {}
    local hi, ri = 0, 0

    local function addHeader(label, y)
        hi = hi + 1
        local r = headers[hi]
        if not r then
            r = menu:CreateFontString(nil, "OVERLAY", "GameFontNormalSmall")
            headers[hi] = r
        end
        r:ClearAllPoints()
        r:SetPoint("TOPLEFT", 10, y)
        r:SetText(label)
        r:Show()
        return y - 16
    end

    local function addRow(c, y, width)
        ri = ri + 1
        local r = rows[ri]
        if not r then
            r = CreateFrame("Button", nil, menu)
            r:SetHeight(18)
            local fs = r:CreateFontString(nil, "OVERLAY", "GameFontNormal")
            fs:SetPoint("LEFT", 6, 0)
            r:SetFontString(fs); r.text = fs
            r:SetHighlightTexture("Interface\\QuestFrame\\UI-QuestTitleHighlight")
            rows[ri] = r
        end
        r:SetWidth(width - 16)
        r:ClearAllPoints()
        r:SetPoint("TOPLEFT", 8, y)
        local label = c.name or "?"
        if c.color and c.color ~= "" then
            label = "|cff" .. c.color .. label .. "|r"   -- class colour
        end
        r.text:SetText(label)
        r.cdata = c
        r:SetScript("OnClick", function() menu:Hide(); switchTo(c) end)
        r:SetScript("OnEnter", function(self)
            local cd = self.cdata
            if not cd then return end
            local card = WowManagerConfig and WowManagerConfig.hoverCard
                         and cd.info and #cd.info > 0
            GameTooltip:SetOwner(self, "ANCHOR_RIGHT")
            if not card then
                GameTooltip:AddLine(cd.name or "?")
                if canSwitchInClient(cd) then
                    GameTooltip:AddLine("Без перезапуска клиента", 0.4, 1, 0.4)
                else
                    GameTooltip:AddLine("С перезапуском клиента", 1, 0.8, 0.3)
                end
                GameTooltip:Show()
                return
            end
            local title = cd.name or "?"
            if cd.color and cd.color ~= "" then
                title = "|cff" .. cd.color .. title .. "|r"
            end
            GameTooltip:AddLine(title)
            for _, line in ipairs(cd.info) do
                GameTooltip:AddLine(line, 1, 1, 1, true)
            end
            if canSwitchInClient(cd) then
                GameTooltip:AddLine("Без перезапуска клиента", 0.4, 1, 0.4)
            else
                GameTooltip:AddLine("С перезапуском клиента", 1, 0.8, 0.3)
            end
            GameTooltip:Show()
        end)
        r:SetScript("OnLeave", function() GameTooltip:Hide() end)
        r:Show()
        return y - 19
    end

    local function showMenu()
        for _, r in ipairs(headers) do r:Hide() end
        for _, r in ipairs(rows) do r:Hide() end
        hi, ri = 0, 0
        local list = (WowManagerConfig and WowManagerConfig.characters) or {}
        local chars, accs = {}, {}
        for _, c in ipairs(list) do
            if c.isAccount then accs[#accs + 1] = c else chars[#chars + 1] = c end
        end
        local y, width = -10, 180
        if #chars > 0 then
            y = addHeader("|cffffd100Персонажи|r", y)
            for _, c in ipairs(chars) do y = addRow(c, y, width) end
        end
        if #accs > 0 then
            y = y - 4
            y = addHeader("|cffffd100Аккаунты|r", y)
            for _, c in ipairs(accs) do y = addRow(c, y, width) end
        end
        menu:SetWidth(width)
        menu:SetHeight(math.max(28, -y + 8))
        menu:ClearAllPoints()
        menu:SetPoint("TOPRIGHT", b, "BOTTOMLEFT", 8, 0)
        menu:Show()
    end

    b:RegisterForClicks("LeftButtonUp", "RightButtonUp")
    b:SetScript("OnClick", function(self, button)
        menu:Hide()
        if button == "RightButton" then
            showMenu()
        else
            toggleAltsWindow()
        end
    end)
    b:SetScript("OnEnter", function(self)
        GameTooltip:SetOwner(self, "ANCHOR_LEFT")
        GameTooltip:AddLine("WoW Manager")
        GameTooltip:AddLine("ЛКМ - окно персонажей", 1, 1, 1)
        GameTooltip:AddLine("ПКМ - быстрое меню перезахода", 1, 1, 1)
        GameTooltip:AddLine("/wm lfg - поиск группы", 1, 1, 1)
        GameTooltip:AddLine("Тащить - двигать кнопку", 1, 1, 1)
        GameTooltip:Show()
    end)
    b:SetScript("OnLeave", function() GameTooltip:Hide() end)
end

-- ── delayed collect ─────────────────────────────────────────────────────────
-- On login the money/currency/lockout data isn't loaded yet (gold reads 0),
-- so we re-collect a few times over the first ~15 seconds. No C_Timer in 3.3.5,
-- so we drive it from an OnUpdate ticker.
local ticker = CreateFrame("Frame")
local acc, nextAt, ticks = 0, 0, 0
ticker:Hide()
ticker:SetScript("OnUpdate", function(self, e)
    acc = acc + e
    if acc >= nextAt then
        collect()
        ticks = ticks + 1
        nextAt = acc + 4              -- every 4s
        if ticks >= 4 then self:Hide() end   -- stop after ~16s
    end
end)
local function startDelayedCollect()
    acc, nextAt, ticks = 0, 2, 0      -- first re-collect at +2s
    ticker:Show()
end

-- ── shared friends & ignore list ───────────────────────────────────────────
-- In 3.3.5 every character has its own friends list. This keeps one list per
-- realm and faction (the game won't take a friend from the other faction) in
-- the account-wide SavedVariables and brings every character in line with it.
--
-- Removals travel too: dropping a friend on one character marks it removed
-- (with a time), and another character that still has it drops it as well —
-- unless that character only picked the friend up after the removal.

local SOCIAL_CAP = 50              -- the game's own limit for both lists
local socialQueue, socialQueued = {}, {}
local socialAdded, socialRemoved = 0, 0
local socialTicker = CreateFrame("Frame")
socialTicker:Hide()

local function socialEnabled()
    return WowManagerConfig and WowManagerConfig.syncFriends
end

local function socialBucket()
    local realm = GetRealmName() or "?"
    local faction = UnitFactionGroup("player") or "?"
    WowManagerDB.__social = WowManagerDB.__social or {}
    local r = WowManagerDB.__social
    r[realm] = r[realm] or {}
    r[realm][faction] = r[realm][faction] or {}
    local b = r[realm][faction]
    b.friends = b.friends or {}
    b.ignore = b.ignore or {}
    b.goneFriends = b.goneFriends or {}
    b.goneIgnore = b.goneIgnore or {}
    return b
end

local SOCIAL_LISTS = {
    friends = {
        read = function()
            local out = {}
            for i = 1, (GetNumFriends() or 0) do
                local name, _, _, _, _, _, note = GetFriendInfo(i)
                if name and name ~= "" then
                    out[foldCase(name)] = { name = name, note = note }
                end
            end
            return out
        end,
        add = function(e)
            AddFriend(e.name)
            if e.note and e.note ~= "" then
                -- The note can only be set once the friend is on the list.
                socialQueue[#socialQueue + 1] = { note = e }
            end
        end,
        del = function(name) RemoveFriend(name) end,
        shared = "friends", gone = "goneFriends", pending = "pendingFriends",
        dropped = "droppedFriends",
        last = "lastFriends", seen = "seenFriends", init = "friendsInit",
    },
    ignore = {
        read = function()
            local out = {}
            for i = 1, (GetNumIgnores() or 0) do
                local name = GetIgnoreName(i)
                if name and name ~= "" and name ~= UNKNOWN then
                    out[foldCase(name)] = { name = name }
                end
            end
            return out
        end,
        add = function(e) AddIgnore(e.name) end,
        del = function(name) DelIgnore(name) end,
        shared = "ignore", gone = "goneIgnore", pending = "pendingIgnore",
        dropped = "droppedIgnore",
        last = "lastIgnore", seen = "seenIgnore", init = "ignoreInit",
    },
}

local function queueAction(key, action)
    if socialQueued[key] then return end
    socialQueued[key] = true
    socialQueue[#socialQueue + 1] = action
    socialTicker:Show()
end

local SOCIAL_CONFIRM = 5            -- seconds a name must stay missing
local scheduleRecheck              -- defined right after syncList

local function syncList(kind)
    if not socialEnabled() then return end
    local L = SOCIAL_LISTS[kind]
    local b = socialBucket()
    local C = WowManagerCharDB
    local shared, gone = b[L.shared], b[L.gone]
    local now = time()
    local me = foldCase(UnitName("player") or "")
    local cur = L.read()

    C[L.seen] = C[L.seen] or {}
    local seen = C[L.seen]
    if not C[L.init] then
        -- First sync on this character: what it already had predates any
        -- removal recorded elsewhere, so those removals win.
        for n in pairs(cur) do seen[n] = 0 end
        C[L.init] = true
    end
    for n in pairs(cur) do
        if seen[n] == nil then seen[n] = now end
    end

    -- 1. removed on this character since the last update.
    -- Right after login the game can report an empty or partial list before
    -- the server has sent the real one, and reading that as "the player
    -- deleted everyone" would wipe the list on every character. So a missing
    -- name is only pending at first; it counts as removed once it is still
    -- missing SOCIAL_CONFIRM seconds later. The real list arriving in between
    -- clears it again.
    C[L.pending] = C[L.pending] or {}
    local pending = C[L.pending]
    for n in pairs(cur) do pending[n] = nil end
    for n in pairs(C[L.last] or {}) do
        if not cur[n] and not pending[n] then pending[n] = now end
    end
    local waiting = false
    for n, since in pairs(pending) do
        if now - since >= SOCIAL_CONFIRM then
            shared[n] = nil
            gone[n] = now
            seen[n] = nil
            pending[n] = nil
        else
            waiting = true
        end
    end
    if waiting then scheduleRecheck() end
    if next(cur) == nil and waiting then
        return          -- most likely the list just isn't loaded yet
    end

    -- 2. removed elsewhere after this character picked it up: drop it here
    --    (once — if it shows up again after we dropped it, the player put it
    --    back on purpose, and that wins over the old removal)
    -- 3. otherwise whatever this character has joins the shared list
    C[L.dropped] = C[L.dropped] or {}
    local dropped = C[L.dropped]
    local count = 0
    for n, info in pairs(cur) do
        count = count + 1
        if gone[n] and dropped[n] then
            dropped[n], gone[n] = nil, nil
            seen[n] = now
            shared[n] = info
        elseif gone[n] and gone[n] >= (seen[n] or 0) then
            queueAction(kind .. "-" .. n, { del = L.del, name = info.name,
                                            key = n, dropped = L.dropped })
        else
            gone[n] = nil
            dropped[n] = nil
            shared[n] = info
        end
    end

    -- 4. add what the other characters have. A name the server refused
    -- twice (deleted character, typo, other faction) is not tried again.
    C.addFails = C.addFails or {}
    C.addTried = C.addTried or {}
    local fails, tried = C.addFails, C.addTried
    for n in pairs(cur) do
        fails[kind .. n], tried[kind .. n] = nil, nil      -- it made it
    end
    for n, info in pairs(shared) do
        local key, qkey = kind .. n, kind .. "+" .. n
        if not cur[n] and not gone[n] and not pending[n] and n ~= me
                and count < SOCIAL_CAP and not socialQueued[qkey] then
            if tried[key] then
                fails[key] = (fails[key] or 0) + 1
                tried[key] = nil
            end
            if (fails[key] or 0) < 2 then
                count = count + 1
                tried[key] = true
                queueAction(qkey, { add = L.add, entry = info })
            end
        end
    end

    local snapshot = {}
    for n in pairs(cur) do snapshot[n] = true end
    C[L.last] = snapshot
end

local socialRecheck = CreateFrame("Frame")
socialRecheck:Hide()
socialRecheck:SetScript("OnUpdate", function(self, elapsed)
    self.left = (self.left or 0) - elapsed
    if self.left > 0 then return end
    self:Hide()
    syncList("friends")
    syncList("ignore")
end)

scheduleRecheck = function()
    if not socialRecheck:IsShown() then
        socialRecheck.left = SOCIAL_CONFIRM + 1
        socialRecheck:Show()
    end
end

socialTicker:SetScript("OnUpdate", function(self, elapsed)
    self.wait = (self.wait or 0) - elapsed
    if self.wait > 0 then return end
    self.wait = 0.5
    local a = table.remove(socialQueue, 1)
    if not a then
        self:Hide()
        socialQueued = {}
        if socialAdded + socialRemoved > 0 then
            DEFAULT_CHAT_FRAME:AddMessage(string.format(
                "|cffE3B341WoW Manager|r: друзья и игнор синхронизированы (+%d, -%d)",
                socialAdded, socialRemoved))
            socialAdded, socialRemoved = 0, 0
        end
        return
    end
    if a.add then
        a.add(a.entry)
        socialAdded = socialAdded + 1
    elseif a.del then
        a.del(a.name)
        local d = WowManagerCharDB[a.dropped] or {}
        d[a.key] = time()
        WowManagerCharDB[a.dropped] = d
        socialRemoved = socialRemoved + 1
    elseif a.note then
        pcall(SetFriendNotes, a.note.name, a.note.note)
    end
end)


-- ── group finder ────────────────────────────────────────────────────────────
-- 3.3.5 has no raid finder, so raids are gathered by spamming chat channels.
-- This reads those messages and keeps a tidy list: which raid, 10/25,
-- heroic, which roles are wanted, what GS is asked for, and who to whisper.

local LFG_TTL = 600                -- seconds an ad stays in the list
local LFG_ROWS, LFG_ROW_H = 14, 22
local lfgEntries = {}              -- author -> ad
local lfgFrame, lfgRows
local lfgFilter, lfgFitsOnly, lfgSound = "ALL", false, false
local lfgLastSound = 0

local LFG_RAIDS = {
    { key = "ICC", label = "ЦЛК", words = { "цлк", "icc", "ицц", "цитадель" } },
    { key = "RS", label = "РС", words = { "рс", "rs", "халион", "halion" } },
    { key = "TOC", label = "ИК", words = { "ик", "toc", "totc", "тотк", "тотгк", "иквк" } },
    { key = "VOA", label = "СА", words = { "са", "воа", "voa", "склеп", "аркавон", "торавон" } },
    { key = "ULD", label = "Ульдуар", words = { "ульд", "ульда", "ульдуар", "uld", "ulduar" } },
    { key = "NAXX", label = "Накс", words = { "накс", "наксрамас", "naxx" } },
    { key = "OS", label = "ОС", words = { "ос", "os", "сарт", "сартарион" } },
    { key = "ONY", label = "Оня", words = { "оня", "ония", "ониксия", "ony", "onyxia" } },
    { key = "EOE", label = "Око", words = { "око", "малигос", "eoe" } },
}
local LFG_WORD, LFG_LABEL = {}, {}
for _, r in ipairs(LFG_RAIDS) do
    LFG_LABEL[r.key] = r.label
    for _, w in ipairs(r.words) do LFG_WORD[w] = r.key end
end
local LFG_ROLE = {
    ["танк"] = "T", ["танки"] = "T", ["танка"] = "T", ["tank"] = "T",
    ["мт"] = "T", ["от"] = "T",
    ["хил"] = "H", ["хилы"] = "H", ["хила"] = "H", ["хилов"] = "H",
    ["хилл"] = "H", ["хилер"] = "H", ["хилеры"] = "H", ["heal"] = "H",
    ["healer"] = "H", ["хилка"] = "H",
    ["дд"] = "D", ["рдд"] = "D", ["мдд"] = "D", ["dd"] = "D", ["rdd"] = "D",
    ["mdd"] = "D", ["дпс"] = "D", ["dps"] = "D", ["рдпс"] = "D", ["мдпс"] = "D",
    ["кастер"] = "D", ["кастеры"] = "D", ["рейндж"] = "D", ["мили"] = "D",
}
local LFG_HEROIC = { ["гер"] = true, ["героик"] = true, ["хм"] = true,
                     ["hc"] = true, ["hm"] = true, ["героич"] = true, ["h"] = true }
local LFG_SEEKER = { ["lfg"] = true, ["ищу"] = true }

local lowerUtf8 = foldCase

local function parseGS(low)
    local best
    for s, num, e in low:gmatch("()(%d+[%.,]?%d*)()") do
        local v = tonumber((num:gsub(",", ".")))
        if v then
            local before = low:sub(math.max(1, s - 8), s - 1)
            local after = low:sub(e, e + 3)
            local marked = before:find("гс") or before:find("gs")
            local kilo = after:find("^%s?к") or after:find("^%s?k")
            if v < 10 and (kilo or marked) then
                v = v * 1000
            elseif v >= 10 and v < 100 and marked then
                v = v * 100
            elseif not (v >= 1000 and (marked or after:find("^%+"))) then
                v = nil
            end
            if v and v >= 1000 and v <= 7000 then
                v = math.floor(v)
                if not best or v > best then best = v end
            end
        end
    end
    return best
end

-- Returns an ad table, or nil when the message isn't about a raid.
local function parseLfg(msg)
    local low = lowerUtf8(msg)
    local ad = { roles = {} }
    for tok in low:gmatch("[%w\128-\255]+") do
        local letters = tok:gsub("%d", "")
        local num = tok:match("%d+")
        if LFG_WORD[letters] and not ad.raid then ad.raid = LFG_WORD[letters] end
        if num == "10" or num == "25" then ad.size = tonumber(num) end
        if LFG_HEROIC[letters] then ad.heroic = true end
        local role = LFG_ROLE[letters]
        if role then ad.roles[role] = true end
        if LFG_SEEKER[letters] then ad.seeker = true end
    end
    if not ad.raid then return nil end
    ad.gs = parseGS(low)
    return ad
end

local function myGearScore()
    local rec = WowManagerDB[(GetRealmName() or "?") .. "." .. (UnitName("player") or "?")]
    return (rec and rec.gs) or computeGearScore()
end

local function lfgVisible(ad)
    if lfgFilter ~= "ALL" and ad.raid ~= lfgFilter then return false end
    if lfgFitsOnly and ad.gs and ad.gs > myGearScore() then return false end
    return true
end

local function lfgSorted()
    local now, list = time(), {}
    for author, ad in pairs(lfgEntries) do
        if now - ad.t > LFG_TTL then
            lfgEntries[author] = nil
        elseif lfgVisible(ad) then
            list[#list + 1] = ad
        end
    end
    table.sort(list, function(a, b) return a.t > b.t end)
    return list
end

local function lfgRoles(ad)
    local out = {}
    if ad.roles.T then out[#out + 1] = "|cff4fa3ffТ|r" end
    if ad.roles.H then out[#out + 1] = "|cff40ff40Х|r" end
    if ad.roles.D then out[#out + 1] = "|cffff6060Д|r" end
    return table.concat(out, " ")
end

local function lfgRaidText(ad)
    local s = LFG_LABEL[ad.raid] or ad.raid
    if ad.size then s = s .. " " .. ad.size end
    if ad.heroic then s = s .. " гер" end
    return s
end

local function lfgRefresh()
    if not (lfgFrame and lfgFrame:IsShown()) then return end
    local list = lfgSorted()
    FauxScrollFrame_Update(lfgFrame.scroll, #list, LFG_ROWS, LFG_ROW_H)
    local offset = FauxScrollFrame_GetOffset(lfgFrame.scroll)
    local now = time()
    local mine = myGearScore()
    for i = 1, LFG_ROWS do
        local row, ad = lfgRows[i], list[i + offset]
        if not ad then
            row:Hide()
        else
            row.ad = ad
            local age = now - ad.t
            row.age:SetText(age < 60 and (age .. "с") or (math.floor(age / 60) .. "м"))
            row.raid:SetText(lfgRaidText(ad))
            row.roles:SetText(lfgRoles(ad))
            local gs = ad.gs and tostring(ad.gs) or "-"
            if ad.gs and ad.gs > mine then gs = "|cffff5050" .. gs .. "|r" end
            row.gs:SetText(gs)
            local c = ad.class and RAID_CLASS_COLORS and RAID_CLASS_COLORS[ad.class]
            local who = ad.author
            if c then
                who = string.format("|cff%02x%02x%02x%s|r", c.r * 255, c.g * 255,
                                    c.b * 255, who)
            end
            if ad.seeker then who = who .. " |cff808080(ищет)|r" end
            row.who:SetText(who)
            row:Show()
        end
    end
    lfgFrame.count:SetText(string.format("Объявлений: %d - мой ГС: %d", #list, mine))
end

local function lfgWhisper(ad)
    local cls = UnitClass("player") or ""
    local rec = WowManagerDB[(GetRealmName() or "?") .. "." .. (UnitName("player") or "?")]
    local spec = rec and rec.spec or ""
    local text = string.format("+ %s %s гс %d", cls, spec, myGearScore())
    ChatFrame_OpenChat("/w " .. ad.author .. " " .. text:gsub("%s+", " "))
end

local function createLfgFrame()
    if lfgFrame then return lfgFrame end
    local f = CreateFrame("Frame", "WowManagerLfgFrame", UIParent)
    f:SetWidth(640); f:SetHeight(440)
    f:SetPoint("CENTER", 0, 40)
    f:SetFrameStrata("HIGH"); f:SetToplevel(true)
    f:SetMovable(true); f:EnableMouse(true); f:SetClampedToScreen(true)
    f:RegisterForDrag("LeftButton")
    f:SetScript("OnDragStart", function(self) self:StartMoving() end)
    f:SetScript("OnDragStop", function(self) self:StopMovingOrSizing() end)
    f:SetBackdrop({
        bgFile = "Interface\\DialogFrame\\UI-DialogBox-Background",
        edgeFile = "Interface\\DialogFrame\\UI-DialogBox-Border",
        tile = true, tileSize = 32, edgeSize = 32,
        insets = { left = 11, right = 12, top = 12, bottom = 11 } })
    f:Hide()

    local title = f:CreateFontString(nil, "OVERLAY", "GameFontNormalLarge")
    title:SetPoint("TOP", 0, -16)
    title:SetText("Поиск группы")
    local close = CreateFrame("Button", nil, f, "UIPanelCloseButton")
    close:SetPoint("TOPRIGHT", -8, -8)

    -- raid filter buttons
    local x = 20
    local filters = { { key = "ALL", label = "Все" } }
    for _, r in ipairs(LFG_RAIDS) do filters[#filters + 1] = r end
    f.filterBtns = {}
    for _, flt in ipairs(filters) do
        local b = CreateFrame("Button", nil, f, "UIPanelButtonTemplate")
        b:SetText(flt.label)
        b:SetHeight(20)
        b:SetWidth(math.max(40, b:GetFontString():GetStringWidth() + 16))
        b:SetPoint("TOPLEFT", x, -44)
        x = x + b:GetWidth() + 2
        b:SetScript("OnClick", function()
            lfgFilter = flt.key
            for _, other in ipairs(f.filterBtns) do other:UnlockHighlight() end
            b:LockHighlight()
            lfgRefresh()
        end)
        if flt.key == "ALL" then b:LockHighlight() end
        f.filterBtns[#f.filterBtns + 1] = b
    end

    local fits = CreateFrame("CheckButton", nil, f, "UICheckButtonTemplate")
    fits:SetWidth(22); fits:SetHeight(22)
    fits:SetPoint("TOPLEFT", 18, -68)
    fits:SetScript("OnClick", function(self)
        lfgFitsOnly = self:GetChecked() and true or false
        lfgRefresh()
    end)
    local fitsText = f:CreateFontString(nil, "OVERLAY", "GameFontHighlightSmall")
    fitsText:SetPoint("LEFT", fits, "RIGHT", 2, 0)
    fitsText:SetText("Только где хватает моего ГС")

    local sound = CreateFrame("CheckButton", nil, f, "UICheckButtonTemplate")
    sound:SetWidth(22); sound:SetHeight(22)
    sound:SetPoint("TOPLEFT", 230, -68)
    sound:SetScript("OnClick", function(self)
        lfgSound = self:GetChecked() and true or false
    end)
    local soundText = f:CreateFontString(nil, "OVERLAY", "GameFontHighlightSmall")
    soundText:SetPoint("LEFT", sound, "RIGHT", 2, 0)
    soundText:SetText("Звук при новом подходящем объявлении")

    -- column headings
    local heads = { { "Когда", 24 }, { "Рейд", 72 }, { "Роли", 200 },
                    { "ГС", 280 }, { "Кто", 340 } }
    for _, h in ipairs(heads) do
        local fs = f:CreateFontString(nil, "OVERLAY", "GameFontNormalSmall")
        fs:SetPoint("TOPLEFT", h[2], -98)
        fs:SetText(h[1])
    end

    local listBg = CreateFrame("Frame", nil, f)
    listBg:SetPoint("TOPLEFT", 16, -112)
    listBg:SetWidth(604); listBg:SetHeight(LFG_ROWS * LFG_ROW_H + 8)
    listBg:SetBackdrop({
        bgFile = "Interface\\ChatFrame\\ChatFrameBackground",
        edgeFile = "Interface\\Tooltips\\UI-Tooltip-Border",
        tile = true, tileSize = 16, edgeSize = 12,
        insets = { left = 3, right = 3, top = 3, bottom = 3 } })
    listBg:SetBackdropColor(0, 0, 0, 0.45)

    local scroll = CreateFrame("ScrollFrame", "WowManagerLfgScroll", listBg,
                               "FauxScrollFrameTemplate")
    scroll:SetPoint("TOPLEFT", 4, -4)
    scroll:SetWidth(576); scroll:SetHeight(LFG_ROWS * LFG_ROW_H)
    scroll:SetScript("OnVerticalScroll", function(self, offset)
        FauxScrollFrame_OnVerticalScroll(self, offset, LFG_ROW_H, lfgRefresh)
    end)
    f.scroll = scroll

    lfgRows = {}
    for i = 1, LFG_ROWS do
        local row = CreateFrame("Button", nil, listBg)
        row:SetWidth(574); row:SetHeight(LFG_ROW_H)
        row:SetPoint("TOPLEFT", 5, -(4 + (i - 1) * LFG_ROW_H))
        row:SetHighlightTexture("Interface\\QuestFrame\\UI-QuestTitleHighlight")
        local function col(x, w, tmpl)
            local fs = row:CreateFontString(nil, "OVERLAY", tmpl or "GameFontHighlightSmall")
            fs:SetPoint("LEFT", x, 0)
            fs:SetWidth(w); fs:SetJustifyH("LEFT")
            return fs
        end
        row.age = col(4, 44, "GameFontDisableSmall")
        row.raid = col(52, 124, "GameFontNormalSmall")
        row.roles = col(180, 76)
        row.gs = col(260, 56)
        row.who = col(320, 250)
        row:SetScript("OnClick", function(self)
            if self.ad then lfgWhisper(self.ad) end
        end)
        row:SetScript("OnEnter", function(self)
            if not self.ad then return end
            GameTooltip:SetOwner(self, "ANCHOR_RIGHT")
            GameTooltip:AddLine(self.ad.author)
            GameTooltip:AddLine(self.ad.text, 1, 1, 1, true)
            GameTooltip:AddLine("Клик - шепнуть с «+ класс спек ГС»", 0.5, 0.8, 1)
            GameTooltip:Show()
        end)
        row:SetScript("OnLeave", function() GameTooltip:Hide() end)
        lfgRows[i] = row
    end

    f.count = f:CreateFontString(nil, "OVERLAY", "GameFontDisableSmall")
    f.count:SetPoint("BOTTOMLEFT", 22, 22)

    local ticker = 0
    f:SetScript("OnUpdate", function(_, elapsed)
        ticker = ticker + elapsed
        if ticker >= 2 then ticker = 0; lfgRefresh() end
    end)
    f:SetScript("OnShow", lfgRefresh)
    tinsert(UISpecialFrames, "WowManagerLfgFrame")
    lfgFrame = f
    return f
end

function toggleLfgWindow()
    if not (WowManagerConfig and WowManagerConfig.lfg) then
        DEFAULT_CHAT_FRAME:AddMessage("|cffE3B341WoW Manager|r: поиск группы "
            .. "выключен в настройках менеджера.")
        return
    end
    local f = createLfgFrame()
    if f:IsShown() then f:Hide() else f:Show() end
end

local function onLfgChat(msg, author, guid)
    if not (WowManagerConfig and WowManagerConfig.lfg) then return end
    if not msg or not author or author == "" or author == UnitName("player") then
        return
    end
    local ad = parseLfg(msg)
    if not ad then return end
    ad.author, ad.text, ad.t = author, msg, time()
    if guid and GetPlayerInfoByGUID then
        local ok, _, class = pcall(GetPlayerInfoByGUID, guid)
        if ok then ad.class = class end
    end
    local isNew = not lfgEntries[author]
    lfgEntries[author] = ad
    if lfgSound and isNew and not ad.seeker and lfgVisible(ad)
            and time() - lfgLastSound > 10 then
        lfgLastSound = time()
        PlaySound("TellMessage")
    end
    lfgRefresh()
end



-- ── harvest mode ────────────────────────────────────────────────────────────
-- The manager can collect data for the whole roster by itself. It launches the
-- account with a list of characters; this walks that list, collecting each one
-- and switching to the next inside the client (no restart), then quits so the
-- manager can move on to the next account. Only runs when asked to.

local harvestStarted = false
local harvestTimer = CreateFrame("Frame")
harvestTimer:Hide()

local function harvestSay(msg)
    DEFAULT_CHAT_FRAME:AddMessage("|cffE3B341WoW Manager|r: " .. msg)
end

local function harvestNext()
    local list = (WowManagerConfig and WowManagerConfig.harvestChars) or {}
    local me = foldCase(UnitName("player") or "")
    for i, name in ipairs(list) do
        if foldCase(name) == me then return list[i + 1] end
    end
    for _, name in ipairs(list) do        -- not on the list: start at the top
        if foldCase(name) ~= me then return name end
    end
end

harvestTimer:SetScript("OnUpdate", function(self, elapsed)
    self.left = (self.left or 0) - elapsed
    if self.left > 0 then return end
    self:Hide()
    collect()
    local nextName = harvestNext()
    if nextName and type(WowManagerSwitchCharacter) == "function" then
        harvestSay("data collected, moving on to " .. nextName)
        WowManagerSwitchCharacter(nextName)
        Logout()
    else
        harvestSay("account done, closing the game")
        Quit()
    end
end)

local function harvestStart()
    if harvestStarted or not (WowManagerConfig and WowManagerConfig.harvest) then
        return
    end
    harvestStarted = true
    if RequestRaidInfo then RequestRaidInfo() end
    if RequestTimePlayed then RequestTimePlayed() end
    harvestTimer.left = tonumber(WowManagerConfig.harvestWait) or 12
    harvestTimer:Show()
    harvestSay("collecting data, don't touch the game")
end


-- ── slash command ───────────────────────────────────────────────────────────
-- Reachable even when the minimap button is switched off in the manager.
SLASH_WOWMANAGER1 = "/wowmanager"
SLASH_WOWMANAGER2 = "/wm"
SlashCmdList["WOWMANAGER"] = function(msg)
    local cmd = lowerUtf8(msg or ""):match("^%s*(%S*)")
    if cmd == "lfg" or cmd == "группа" or cmd == "лфг" then
        toggleLfgWindow()
    else
        toggleAltsWindow()
    end
end


-- ── events ──────────────────────────────────────────────────────────────────
local chat = CreateFrame("Frame")
if WowManagerConfig and WowManagerConfig.lfg then
    chat:RegisterEvent("CHAT_MSG_CHANNEL")
    chat:RegisterEvent("CHAT_MSG_YELL")
    chat:RegisterEvent("CHAT_MSG_SAY")
end
chat:SetScript("OnEvent", function(_, _, msg, author, _, _, _, _, _, _, _, _, _, guid)
    onLfgChat(msg, author, guid)
end)

local f = CreateFrame("Frame")
f:RegisterEvent("PLAYER_LOGIN")
f:RegisterEvent("PLAYER_LOGOUT")
f:RegisterEvent("PLAYER_MONEY")
f:RegisterEvent("UPDATE_INSTANCE_INFO")
f:RegisterEvent("CURRENCY_DISPLAY_UPDATE")
f:RegisterEvent("TIME_PLAYED_MSG")
f:RegisterEvent("PLAYER_ENTERING_WORLD")
f:RegisterEvent("ARENA_TEAM_UPDATE")
f:RegisterEvent("FRIENDLIST_UPDATE")
f:RegisterEvent("IGNORELIST_UPDATE")
f:RegisterEvent("LOGOUT_CANCEL")
f:SetScript("OnEvent", function(self, event, arg1)
    if event == "PLAYER_LOGIN" then
        -- We are the session the manager relaunched (or the player just logged
        -- in normally). Either way the pending request is spent — leaving it in
        -- SavedVariables means the manager can act on it again later.
        WowManagerDB.__relog = nil
        if RequestRaidInfo then RequestRaidInfo() end
        if RequestTimePlayed then RequestTimePlayed() end
        if socialEnabled() and ShowFriends then ShowFriends() end
        collect()
        if WowManagerConfig and WowManagerConfig.showMinimap then
            createMinimapButton()
        end
    elseif event == "PLAYER_ENTERING_WORLD" then
        collect()
        startDelayedCollect()         -- gold/currency arrive shortly after
        harvestStart()
    elseif event == "FRIENDLIST_UPDATE" then
        syncList("friends")
    elseif event == "IGNORELIST_UPDATE" then
        syncList("ignore")
    elseif event == "LOGOUT_CANCEL" then
        -- Drop the armed target only if we turn out to still be in the world
        -- (see cancelWatch). The DLL also expires a request on its own after
        -- a minute, so nothing lingers either way.
        cancelWatch.left = 3
        cancelWatch:Show()
    elseif event == "TIME_PLAYED_MSG" then
        WowManagerCharDB.played = arg1
        collect()
    else
        collect()
    end
end)
