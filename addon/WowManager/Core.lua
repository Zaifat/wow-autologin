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
function computeGearScore()
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
local function try(fn) local ok = pcall(fn); return ok end

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

    if WowManagerCharDB.played then d.played = WowManagerCharDB.played end

    WowManagerDB[ckey()] = d     -- ALWAYS save
end

-- ── relog request (overlay) ────────────────────────────────────────────────
-- Write the target + quit; the manager sees the request after Wow.exe closes
-- and relaunches the chosen character/account.
local function requestRelog(account, char)
    WowManagerDB.__relog = { account = account, char = char, at = time() }
    Quit()
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
    local rows = {}
    local ri = 0

    local function addHeader(label, y, width)
        ri = ri + 1
        local r = rows[ri]
        if not r then
            r = menu:CreateFontString(nil, "OVERLAY", "GameFontNormalSmall")
            rows[ri] = r
        end
        if r.SetScript then r:Hide() end
        r:SetPoint("TOPLEFT", 10, y)
        r:SetText(label)
        r:Show()
        return y - 16
    end

    local function addRow(c, y, width)
        ri = ri + 1
        local r = rows[ri]
        if not r or not r.SetScript then
            r = CreateFrame("Button", nil, menu)
            r:SetHeight(18)
            local fs = r:CreateFontString(nil, "OVERLAY", "GameFontNormal")
            fs:SetPoint("LEFT", 6, 0)
            r:SetFontString(fs); r.text = fs
            r:SetHighlightTexture("Interface\\QuestFrame\\UI-QuestTitleHighlight")
            rows[ri] = r
        end
        r:SetWidth(width - 16)
        r:SetPoint("TOPLEFT", 8, y)
        local label = c.name or "?"
        if c.color and c.color ~= "" then
            label = "|cff" .. c.color .. label .. "|r"   -- class colour
        end
        r.text:SetText(label)
        r.cdata = c
        local acc, nm = c.account, c.name
        r:SetScript("OnClick", function() menu:Hide(); requestRelog(acc, nm) end)
        r:SetScript("OnEnter", function(self)
            local cd = self.cdata
            if not (WowManagerConfig and WowManagerConfig.hoverCard) then return end
            if not (cd and cd.info and #cd.info > 0) then return end
            GameTooltip:SetOwner(self, "ANCHOR_RIGHT")
            local title = cd.name or "?"
            if cd.color and cd.color ~= "" then
                title = "|cff" .. cd.color .. title .. "|r"
            end
            GameTooltip:AddLine(title)
            for _, line in ipairs(cd.info) do
                GameTooltip:AddLine(line, 1, 1, 1, true)
            end
            GameTooltip:Show()
        end)
        r:SetScript("OnLeave", function() GameTooltip:Hide() end)
        r:Show()
        return y - 19
    end

    local function showMenu()
        for _, r in ipairs(rows) do if r.Hide then r:Hide() end end
        ri = 0
        local list = (WowManagerConfig and WowManagerConfig.characters) or {}
        local chars, accs = {}, {}
        for _, c in ipairs(list) do
            if c.isAccount then accs[#accs + 1] = c else chars[#chars + 1] = c end
        end
        local y, width = -10, 180
        if #chars > 0 then
            y = addHeader("|cffffd100Персонажи|r", y, width)
            for _, c in ipairs(chars) do y = addRow(c, y, width) end
        end
        if #accs > 0 then
            y = y - 4
            y = addHeader("|cffffd100Аккаунты|r", y, width)
            for _, c in ipairs(accs) do y = addRow(c, y, width) end
        end
        menu:SetWidth(width)
        menu:SetHeight(math.max(28, -y + 8))
        menu:ClearAllPoints()
        menu:SetPoint("TOPRIGHT", b, "BOTTOMLEFT", 8, 0)
        menu:Show()
    end

    b:RegisterForClicks("LeftButtonUp")
    b:SetScript("OnClick", function()
        if menu:IsShown() then menu:Hide() else showMenu() end
    end)
    b:SetScript("OnEnter", function(self)
        GameTooltip:SetOwner(self, "ANCHOR_LEFT")
        GameTooltip:AddLine("WoW Manager")
        GameTooltip:AddLine("Клик — перезайти, тащить — двигать", 1, 1, 1)
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

-- ── events ──────────────────────────────────────────────────────────────────
local f = CreateFrame("Frame")
f:RegisterEvent("PLAYER_LOGIN")
f:RegisterEvent("PLAYER_LOGOUT")
f:RegisterEvent("PLAYER_MONEY")
f:RegisterEvent("UPDATE_INSTANCE_INFO")
f:RegisterEvent("CURRENCY_DISPLAY_UPDATE")
f:RegisterEvent("TIME_PLAYED_MSG")
f:RegisterEvent("PLAYER_ENTERING_WORLD")
f:SetScript("OnEvent", function(self, event, arg1)
    if event == "PLAYER_LOGIN" then
        if RequestRaidInfo then RequestRaidInfo() end
        if RequestTimePlayed then RequestTimePlayed() end
        collect()
        if WowManagerConfig and WowManagerConfig.showMinimap then
            createMinimapButton()
        end
    elseif event == "PLAYER_ENTERING_WORLD" then
        collect()
        startDelayedCollect()         -- gold/currency arrive shortly after
    elseif event == "TIME_PLAYED_MSG" then
        WowManagerCharDB.played = arg1
        collect()
    else
        collect()
    end
end)
