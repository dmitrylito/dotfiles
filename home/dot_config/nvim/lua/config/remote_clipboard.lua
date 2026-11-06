-- Clipboard for Herdr and SSH sessions whose yanks may need to reach another
-- machine. Paste prefers Wayland locally, then this session's own yanks; an
-- OSC 52 read query blocks up to 10s when the terminal never answers, so it is
-- opt-in via vim.g.remote_clipboard_osc52_paste = true.
local M = {}

local last_yank = {}

local function proc_lines(pid, file)
  local ok, lines = pcall(vim.fn.readfile, "/proc/" .. pid .. "/" .. file)
  return ok and lines or {}
end

local function proc_ppid(pid)
  for _, line in ipairs(proc_lines(pid, "status")) do
    local ppid = line:match("^PPid:%s+(%d+)")
    if ppid then
      return tonumber(ppid)
    end
  end
end

local function ancestor_process_named(name)
  local pid = vim.fn.getpid()

  for _ = 1, 16 do
    local ppid = proc_ppid(pid)
    if not ppid or ppid <= 1 then
      return false
    end

    local comm = proc_lines(ppid, "comm")[1] or ""
    if comm:find(name, 1, true) then
      return true
    end

    pid = ppid
  end

  return false
end

function M.setup()
  local in_ssh = vim.env.SSH_TTY ~= nil or vim.env.SSH_CONNECTION ~= nil
  local in_herdr = vim.env.HERDR_PANE_ID ~= nil or ancestor_process_named("herdr")

  if not (in_ssh or in_herdr) then
    return
  end

  local osc52 = require("vim.ui.clipboard.osc52")
  local has_wayland = vim.env.WAYLAND_DISPLAY ~= nil
    and vim.fn.executable("wl-copy") == 1
    and vim.fn.executable("wl-paste") == 1

  local function copy(register)
    local emit = osc52.copy(register)

    return function(lines, regtype)
      last_yank[register] = { lines, regtype or "v" }

      if has_wayland then
        local cmd = { "wl-copy", "--sensitive", "--type", "text/plain" }
        if register == "*" then
          cmd[#cmd + 1] = "--primary"
        end
        vim.fn.system(cmd, lines)
      end

      if vim.g.omarchy_remote_clipboard_osc52 ~= false then
        emit(lines)
      end
    end
  end

  local function paste(register)
    if has_wayland then
      return function()
        local cmd = { "wl-paste", "--no-newline" }
        if register == "*" then
          cmd[#cmd + 1] = "--primary"
        end

        local lines = vim.fn.systemlist(cmd, "", 1)
        return vim.v.shell_error == 0 and lines or {}
      end
    end

    local query = osc52.paste(register)

    return function()
      if last_yank[register] then
        return last_yank[register]
      end

      if vim.g.remote_clipboard_osc52_paste == true then
        return query()
      end

      return { vim.fn.split(vim.fn.getreg(""), "\n"), vim.fn.getregtype("") }
    end
  end

  vim.g.clipboard = {
    name = "OmarchyRemoteClipboard",
    copy = { ["+"] = copy("+"), ["*"] = copy("*") },
    paste = { ["+"] = paste("+"), ["*"] = paste("*") },
    cache_enabled = 0,
  }
end

return M
