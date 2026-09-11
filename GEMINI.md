# ♊ Gemini & Antigravity Agent Guide

Welcome, Gemini! This file contains critical context, rules, and preferences for AI agents collaborating on this system's dotfiles and workspace.

---

## 💻 System Environments & Profiles

This is a multi-platform environment managed by **Chezmoi**. The active machine profile is determined by the Chezmoi `.profile` template variable.

*   **Mac Profile (`mac`)**:
    *   **OS**: macOS (Darwin)
    *   **Terminal**: **Ghostty** (Aesthetic, Zig-based terminal)
    *   **Window Manager**: **AeroSpace** (Keyboard-driven tiling window manager)
    *   **Theme**: Catppuccin Mocha with a pure black background override
*   **Omarchy Profile (`omarchy`)**:
    *   **OS**: Arch Linux (Omarchy Framework)
    *   **Terminal**: **Ghostty**
    *   **Window Manager**: **Hyprland** (Wayland compositor)
    *   **Theme**: Managed dynamically via `~/.config/omarchy/current/theme/`

---

## 🛠️ Critical Workflow Guidelines

### 1. Chezmoi Dotfiles Management (Absolute Rule)
Do **NOT** write to config target locations directly (e.g., `~/.config/ghostty/config`, `~/.zshrc`). They will be overwritten.
*   **Source Location**: Make all edits in `~/.local/share/chezmoi/`.
*   **Deployment**: Preview with `chezmoi apply --dry-run -v <target>`, then apply only the intended targets with `chezmoi apply <target>`. Preserve unrelated live changes.
*   **Ignored Files**: Be aware of `.chezmoiignore` rules that restrict certain configurations to specific profiles.

### 2. Multi-Profile Templating
When adding or updating configuration files, use Chezmoi's templating features (`.tmpl` extension) to branch between platforms cleanly:
```ini
{{ if eq .profile "omarchy" -}}
# Linux/Omarchy specific settings
{{- else if eq .profile "mac" -}}
# macOS specific settings
{{- end }}
```

### 3. Ghostty Customization Standards
Our Ghostty terminal configuration has been highly optimized and has specific design rules:
*   **Aesthetic Padding**: Keep `window-padding-x = 20` and `window-padding-y = 20` on Mac to maintain a premium visual padding.
*   **Pure Black Background**: Always set `background = 000000` on Mac. This successfully overrides the default background of the built-in `"Catppuccin Mocha"` theme.
*   **No Fallback Import Overrides**: Avoid loading external `.conf` themes via `config-file` after background overrides, as Ghostty evaluates `config-file` imports last, which can overwrite the black background back to theme defaults.

---

## 📜 Active Context & Recent Updates (June 2026)

*   **Terminal Transition**: Switched from iTerm2 to Ghostty on macOS.
*   **Ghostty Integration**: Set up clean, template-based configurations in Chezmoi that cleanly separate macOS and Omarchy preferences.
*   **Window Shadows**: Discovered that macOS window shadows cannot be disabled globally without disabling SIP (System Integrity Protection). Consequently, shadow properties are managed directly inside application configurations (like Ghostty) to keep the AeroSpace workspace looking modern and sharp.
