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
           and entry.account:lower() == mine:lower()
end

-- Logging out lands us on the character select of the realm we are already
-- connected to, so a character on a DIFFERENT realm is not reachable that way
-- even on the same account. An entry with no realm set is assumed to be here.
local function sameRealmAs(entry)
    local want = entry.realm
    if not want or want == "" then return true end
    local here = GetRealmName()
    return here and here:lower() == want:lower()
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

local function switchTo(entry)
    if canSwitchInClient(entry) then
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
    listBg:SetPoint("TOPLEFT", 18, -46)
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
    hint:SetPoint("BOTTOMLEFT", 22, 26)
    hint:SetWidth(270); hint:SetJustifyH("LEFT")
    hint:SetText("Двойной клик по строке — зайти сразу.")

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
        GameTooltip:AddLine("ЛКМ — окно персонажей", 1, 1, 1)
        GameTooltip:AddLine("ПКМ — быстрое меню перезахода", 1, 1, 1)
        GameTooltip:AddLine("Тащить — двигать кнопку", 1, 1, 1)
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

-- ── slash command ───────────────────────────────────────────────────────────
-- Reachable even when the minimap button is switched off in the manager.
SLASH_WOWMANAGER1 = "/wowmanager"
SLASH_WOWMANAGER2 = "/wm"
SlashCmdList["WOWMANAGER"] = function() toggleAltsWindow() end


-- ── events ──────────────────────────────────────────────────────────────────
local f = CreateFrame("Frame")
f:RegisterEvent("PLAYER_LOGIN")
f:RegisterEvent("PLAYER_LOGOUT")
f:RegisterEvent("PLAYER_MONEY")
f:RegisterEvent("UPDATE_INSTANCE_INFO")
f:RegisterEvent("CURRENCY_DISPLAY_UPDATE")
f:RegisterEvent("TIME_PLAYED_MSG")
f:RegisterEvent("PLAYER_ENTERING_WORLD")
f:RegisterEvent("ARENA_TEAM_UPDATE")
f:RegisterEvent("LOGOUT_CANCEL")
f:SetScript("OnEvent", function(self, event, arg1)
    if event == "PLAYER_LOGIN" then
        -- We are the session the manager relaunched (or the player just logged
        -- in normally). Either way the pending request is spent — leaving it in
        -- SavedVariables means the manager can act on it again later.
        WowManagerDB.__relog = nil
        if RequestRaidInfo then RequestRaidInfo() end
        if RequestTimePlayed then RequestTimePlayed() end
        collect()
        if WowManagerConfig and WowManagerConfig.showMinimap then
            createMinimapButton()
        end
    elseif event == "PLAYER_ENTERING_WORLD" then
        collect()
        startDelayedCollect()         -- gold/currency arrive shortly after
    elseif event == "LOGOUT_CANCEL" then
        -- Player moved and the countdown stopped: drop the armed target so the
        -- next, unrelated logout doesn't silently switch characters.
        if type(WowManagerSwitchCharacter) == "function" then
            WowManagerSwitchCharacter("")
        end
    elseif event == "TIME_PLAYED_MSG" then
        WowManagerCharDB.played = arg1
        collect()
    else
        collect()
    end
end)
