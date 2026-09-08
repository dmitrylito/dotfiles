# Omarchy Notification Center

An optional bar widget for reviewing notifications handled by Omarchy's
built-in notification service.

It adds:

- a list of recent notifications with relative timestamps;
- per-notification dismissal and a Clear action;
- a Do Not Disturb toggle (right-click the bell, or the pill in the popup);
- an IPC toggle for keybinds: `omarchy-shell notification-center toggle`.

The notification daemon, toast popups, history storage, DND state, and the
standard DND indicator remain part of Omarchy itself. This plugin only provides
the bar popup for browsing that history.

> **Local fork (2026-08-15):** rewritten in place against the current Omarchy
> notifications service, which dropped `pendingModel`/`pastModel` in favor of
> `popupModel` plus one JSON file per past notification under
> `~/.local/state/omarchy/notifications/history/`. The upstream repo below
> still targets the old API — do NOT `omarchy plugin update` this plugin
> from upstream until it catches up, or the widget breaks again.

## Install

```bash
omarchy plugin add https://github.com/omacom-io/omarchy-notification-center-plugin.git --enable
```

The widget can be positioned explicitly:

```bash
omarchy bar plugin move omacom.notification-center --section right
```

## Development

Validate the manifest and entry point:

```bash
omarchy plugin validate .
```

After changing plugin files:

```bash
omarchy plugin rescan
omarchy restart shell
```

## License

MIT
