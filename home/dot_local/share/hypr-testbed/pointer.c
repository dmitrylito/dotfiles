// hypr-testbed-pointer — a virtual mouse for the hypr-testbed compositor, through
// zwlr_virtual_pointer_v1. It talks only to $WAYLAND_DISPLAY, so it must be run
// with the testbed's display (hypr-testbed pointer does that); ydotool/dotool go
// through uinput and would move the real mouse in the live session.
//
// Built on first use by hypr-testbed into $XDG_RUNTIME_DIR/hypr-testbed/pointer
// from this file and wlr-virtual-pointer-unstable-v1.xml (wlr-protocols, MIT)
// beside it.
//
// Hyprland maps motion_absolute onto the bounding box of all monitors, so an
// absolute position is layout X,Y within the layout's W x H.

#include <linux/input-event-codes.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <time.h>
#include <wayland-client.h>
#include "wlr-virtual-pointer-unstable-v1-client-protocol.h"

static struct wl_seat *seat;
static struct zwlr_virtual_pointer_manager_v1 *manager;

static void global(void *data, struct wl_registry *registry, uint32_t name, const char *interface, uint32_t version) {
  if (!strcmp(interface, wl_seat_interface.name) && !seat)
    seat = wl_registry_bind(registry, name, &wl_seat_interface, 1);
  else if (!strcmp(interface, zwlr_virtual_pointer_manager_v1_interface.name))
    manager = wl_registry_bind(registry, name, &zwlr_virtual_pointer_manager_v1_interface, 1);
}
static void global_remove(void *data, struct wl_registry *registry, uint32_t name) {}
static const struct wl_registry_listener registry_listener = { global, global_remove };

static uint32_t now_ms(void) {
  struct timespec ts;
  clock_gettime(CLOCK_MONOTONIC, &ts);
  return ts.tv_sec * 1000 + ts.tv_nsec / 1000000;
}

static void sleep_ms(long ms) {
  struct timespec ts = { ms / 1000, (ms % 1000) * 1000000 };
  nanosleep(&ts, NULL);
}

static int button_code(const char *name) {
  if (!strcmp(name, "left")) return BTN_LEFT;
  if (!strcmp(name, "right")) return BTN_RIGHT;
  if (!strcmp(name, "middle")) return BTN_MIDDLE;
  return -1;
}

static void usage(void) {
  fprintf(stderr,
    "usage: hypr-testbed-pointer STEP...\n"
    "  abs X Y W H        absolute motion: X,Y within a W x H extent\n"
    "  rel DX DY          relative motion\n"
    "  down|up|click BTN  left, right or middle\n"
    "  scroll N           N wheel steps, positive is down\n"
    "  wait MS\n");
  exit(2);
}

int main(int argc, char **argv) {
  if (argc < 2) usage();
  struct wl_display *display = wl_display_connect(NULL);
  if (!display) { fprintf(stderr, "hypr-testbed-pointer: no Wayland display\n"); return 1; }
  struct wl_registry *registry = wl_display_get_registry(display);
  wl_registry_add_listener(registry, &registry_listener, NULL);
  wl_display_roundtrip(display);
  if (!manager) { fprintf(stderr, "hypr-testbed-pointer: compositor has no zwlr_virtual_pointer_manager_v1\n"); return 1; }
  struct zwlr_virtual_pointer_v1 *pointer = zwlr_virtual_pointer_manager_v1_create_virtual_pointer(manager, seat);
  wl_display_roundtrip(display);

  for (int i = 1; i < argc; i++) {
    const char *step = argv[i];
    if (!strcmp(step, "abs") && i + 4 < argc) {
      zwlr_virtual_pointer_v1_motion_absolute(pointer, now_ms(), atoi(argv[i + 1]), atoi(argv[i + 2]),
                                              atoi(argv[i + 3]), atoi(argv[i + 4]));
      i += 4;
    } else if (!strcmp(step, "rel") && i + 2 < argc) {
      zwlr_virtual_pointer_v1_motion(pointer, now_ms(), wl_fixed_from_double(atof(argv[i + 1])),
                                     wl_fixed_from_double(atof(argv[i + 2])));
      i += 2;
    } else if ((!strcmp(step, "down") || !strcmp(step, "up") || !strcmp(step, "click")) && i + 1 < argc) {
      int code = button_code(argv[++i]);
      if (code < 0) usage();
      if (strcmp(step, "up")) {
        zwlr_virtual_pointer_v1_button(pointer, now_ms(), code, WL_POINTER_BUTTON_STATE_PRESSED);
        zwlr_virtual_pointer_v1_frame(pointer);
        wl_display_roundtrip(display);
      }
      if (!strcmp(step, "click")) sleep_ms(30);
      if (strcmp(step, "down"))
        zwlr_virtual_pointer_v1_button(pointer, now_ms(), code, WL_POINTER_BUTTON_STATE_RELEASED);
    } else if (!strcmp(step, "scroll") && i + 1 < argc) {
      int steps = atoi(argv[++i]);
      zwlr_virtual_pointer_v1_axis_source(pointer, WL_POINTER_AXIS_SOURCE_WHEEL);
      zwlr_virtual_pointer_v1_axis_discrete(pointer, now_ms(), WL_POINTER_AXIS_VERTICAL_SCROLL,
                                            wl_fixed_from_int(15 * steps), steps);
    } else if (!strcmp(step, "wait") && i + 1 < argc) {
      sleep_ms(atol(argv[++i]));
      continue;
    } else {
      usage();
    }
    zwlr_virtual_pointer_v1_frame(pointer);
    wl_display_roundtrip(display);
  }

  zwlr_virtual_pointer_v1_destroy(pointer);
  wl_display_roundtrip(display);
  wl_display_disconnect(display);
  return 0;
}
