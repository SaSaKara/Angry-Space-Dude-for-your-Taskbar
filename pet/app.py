import io
import os
import random
import sys
import time
import tkinter as tk

from pet.consts import OS_DARWIN
from pet.utils import get_work_area


class Pet:
    def __init__(self):
        # Base directory:
        # - Python script mode -> project root
        # - EXE mode -> folder containing the executable
        if getattr(sys, "frozen", False):
            base_dir = os.path.dirname(sys.executable)
        else:
            base_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

        assets_dir = os.path.join(base_dir, "assets")
        icon_path = os.path.join(base_dir, "icon.ico")

        self._is_macos = sys.platform == OS_DARWIN

        # === Tk root (event loop on all platforms, display on Windows only) ===
        self.window = tk.Tk()

        if self._is_macos:
            self._init_macos_display()
        else:
            self._init_windows_display(icon_path)

        # === Load animations from assets folder ===
        def load_frames(filename):
            path = os.path.join(assets_dir, filename)
            if not os.path.exists(path):
                return []

            if self._is_macos:
                return self._load_frames_macos(path)
            return self._load_frames_tk(path)

        self.frames = {
            "walk_right": load_frames("walking_right.gif"),
            "walk_left": load_frames("walking_left.gif"),
            "fire_right": load_frames("fire_right.gif"),
            "fire_left": load_frames("fire_left.gif"),
            "fire": load_frames("fire.gif"),
            "idle_right": load_frames("idle_right.gif"),
            "idle_left": load_frames("idle_left.gif"),
            "sway_right": load_frames("sway_right.gif"),
            "sway_left": load_frames("sway_left.gif"),
            "sway": load_frames("sway.gif"),
            "descend": load_frames("descend.gif"),
        }

        if not self.frames["walk_right"]:
            raise RuntimeError("assets/walking_right.gif not found or empty!")

        # Fallbacks
        if not self.frames["walk_left"]:
            self.frames["walk_left"] = self.frames["walk_right"]

        if not self.frames["fire_right"] and self.frames["fire"]:
            self.frames["fire_right"] = self.frames["fire"]

        if not self.frames["fire_left"] and self.frames["fire"]:
            self.frames["fire_left"] = self.frames["fire"]

        if not self.frames["idle_right"]:
            self.frames["idle_right"] = [self.frames["walk_right"][0]]

        if not self.frames["idle_left"]:
            self.frames["idle_left"] = [self.frames["walk_left"][0]]

        if not self.frames["descend"]:
            self.frames["descend"] = self.frames["idle_right"]

        if not self.frames["sway_right"] and self.frames["sway"]:
            self.frames["sway_right"] = self.frames["sway"]

        if not self.frames["sway_left"] and self.frames["sway"]:
            self.frames["sway_left"] = self.frames["sway"]

        # Default state/parameters
        self.state = "walk"  # walk | fire | idle | drag | descend
        self.direction = 1   # 1: right, -1: left
        self.paused = False

        # Frame timings
        self.frame_time = {
            "walk": 0.08,
            "fire": 0.07,
            "idle": 0.3,
            "sway": 0.09,
            "descend": 0.07,
        }

        self._acc = 0.0
        self._last_t = time.perf_counter()
        self.frame_index = 0

        # Drag & drop
        self._drag = None

        if not self._is_macos:
            # --- Tk-only visual setup ---
            self.label = tk.Label(self.window, bd=0, bg="black")
            self.label.pack()
            self.label.bind("<Button-3>", self.show_menu)
            self.label.bind("<Button-1>", self.start_drag)
            self.label.bind("<B1-Motion>", self.on_drag)
            self.label.bind("<ButtonRelease-1>", self.end_drag)

            # --- Right-click menu ---
            self.menu = tk.Menu(self.window, tearoff=0)
            self.menu.add_command(label="Pause/Resume (Space)", command=self.toggle_pause)
            self.menu.add_separator()
            self.menu.add_command(label="Exit", command=self._quit)

        # Work area and ground
        l, t, r, b = get_work_area()
        self.screen_left = l
        self.screen_top = t
        self.screen_right = r
        self.screen_bottom = b

        # Initial image
        self.current_frames = self.frames["walk_right"]
        self._set_frame(self.frame_index)

        # Spawn from above
        self.x = self.screen_left
        self.y = self.screen_top - self.h
        self._move_window()

        # Ground aligned to work area bottom
        self.ground_y = self.screen_bottom - self.h

        # Horizontal movement
        self.speed = 2

        # Gravity
        self.gravity = 3000.0
        self.vy = 0.0
        self.has_landed_once = False

        # Fire / Idle behavior
        self.FIRE_MIN = 3.0
        self.FIRE_MAX = 8.0
        self.FIRE_DURATION = 1.2

        self.IDLE_MIN = 4.0
        self.IDLE_MAX = 10.0
        self.IDLE_DURATION = 1.5

        self.DESCEND_DURATION = 0.8

        now = time.perf_counter()
        self.next_fire_time = now + random.uniform(self.FIRE_MIN, self.FIRE_MAX)
        self.fire_until = None
        self.next_idle_time = now + random.uniform(self.IDLE_MIN, self.IDLE_MAX)
        self.idle_until = None
        self.descend_until = None

        # Random U-turn timer
        self.TURN_MIN = 5.0
        self.TURN_MAX = 15.0
        self.next_turn_time = now + random.uniform(self.TURN_MIN, self.TURN_MAX)

        # Shortcuts (Tk-only; macOS uses NSEvent monitors set up in _init_macos_display)
        if not self._is_macos:
            self.window.bind("<Escape>", lambda e: self._quit())
            self.window.bind("<space>", lambda e: self.toggle_pause())

        # Loop
        self.update()
        self.window.mainloop()

    def _init_macos_display(self):
        """Create a native transparent NSWindow; hide the Tk root."""
        self.window.withdraw()

        from AppKit import (
            NSWindow, NSBackingStoreBuffered, NSColor,
            NSImageView, NSImage, NSData, NSMakeRect,
            NSScreen, NSEvent,
            NSLeftMouseDownMask, NSLeftMouseDraggedMask,
            NSLeftMouseUpMask, NSRightMouseDownMask,
            NSKeyDownMask,
            NSMenu, NSMenuItem,
        )

        self._NSImage = NSImage
        self._NSData = NSData
        self._NSMakeRect = NSMakeRect
        self._screen_h = float(NSScreen.mainScreen().frame().size.height)

        # Create transparent NSWindow (same recipe as ClearMenuBar)
        self._ns_window = NSWindow.alloc().initWithContentRect_styleMask_backing_defer_(
            NSMakeRect(0, 0, 128, 128), 0, NSBackingStoreBuffered, False,
        )
        self._ns_window.setOpaque_(False)
        self._ns_window.setBackgroundColor_(NSColor.clearColor())
        self._ns_window.setHasShadow_(False)
        self._ns_window.setLevel_(25)  # NSStatusWindowLevel
        self._ns_window.setAcceptsMouseMovedEvents_(True)

        self._ns_image_view = NSImageView.alloc().initWithFrame_(NSMakeRect(0, 0, 128, 128))
        self._ns_image_view.setImageScaling_(0)  # NSImageScaleNone
        self._ns_window.setContentView_(self._ns_image_view)
        self._ns_window.orderFront_(None)

        # --- Right-click menu (native) ---
        self._ns_menu = NSMenu.alloc().init()
        pause_item = NSMenuItem.alloc().initWithTitle_action_keyEquivalent_(
            "Pause/Resume (Space)", None, "",
        )
        exit_item = NSMenuItem.alloc().initWithTitle_action_keyEquivalent_(
            "Exit", None, "",
        )
        self._ns_menu.addItem_(pause_item)
        self._ns_menu.addItem_(NSMenuItem.separatorItem())
        self._ns_menu.addItem_(exit_item)

        # --- Mouse event monitors ---
        mouse_mask = (
            NSLeftMouseDownMask | NSLeftMouseDraggedMask |
            NSLeftMouseUpMask | NSRightMouseDownMask
        )
        pet = self  # prevent closure over self

        def mouse_handler(event):
            if event.window() is not None and event.window() != pet._ns_window:
                return event

            etype = event.type()
            loc = event.locationInWindow()
            local_x = int(loc.x)
            local_y = pet.h - int(loc.y)  # flip Y to top-origin

            if etype == 1:  # NSLeftMouseDown
                pet.start_drag_native(local_x, local_y)
            elif etype == 6:  # NSLeftMouseDragged
                pet.on_drag_native(event)
            elif etype == 2:  # NSLeftMouseUp
                pet.end_drag_native(local_x, local_y)
            elif etype == 3:  # NSRightMouseDown
                # Show context menu
                idx = pet._ns_menu.indexOfItemWithTitle_("Pause/Resume (Space)")
                if idx >= 0:
                    item = pet._ns_menu.itemAtIndex_(idx)
                    item.setTitle_(
                        "Resume (Space)" if pet.paused else "Pause (Space)"
                    )
                NSMenu.popUpContextMenu_withEvent_forView_(
                    pet._ns_menu, event, pet._ns_image_view,
                )
                # Check which item was selected (by checking state change)
                # Use simpler approach: named items
            return event

        NSEvent.addLocalMonitorForEventsMatchingMask_handler_(mouse_mask, mouse_handler)

        # --- Keyboard event monitor ---
        def key_handler(event):
            kc = event.keyCode()
            if kc == 53:  # Escape
                pet._quit()
            elif kc == 49:  # Space
                pet.toggle_pause()
            return event

        NSEvent.addLocalMonitorForEventsMatchingMask_handler_(NSKeyDownMask, key_handler)

        # Intercept NSMenu item clicks
        self._ns_menu_pause = self._ns_menu.itemAtIndex_(0)
        self._ns_menu_exit = self._ns_menu.itemAtIndex_(2)

    def _init_windows_display(self, icon_path):
        """Set up Tk window for Windows (original approach)."""
        self.window.overrideredirect(True)
        self.window.attributes("-topmost", True)
        self.window.config(highlightbackground="black")
        try:
            self.window.wm_attributes("-transparentcolor", "black")
        except tk.TclError:
            pass

        if os.path.exists(icon_path):
            try:
                self.window.iconbitmap(icon_path)
            except Exception:
                pass

    def _load_frames_macos(self, path):
        """Load GIF frames as NSImage objects via Pillow."""
        from PIL import Image

        frames = []
        img = Image.open(path)
        for i in range(img.n_frames):
            img.seek(i)
            rgba = img.convert("RGBA")
            buf = io.BytesIO()
            rgba.save(buf, format="PNG")
            png_bytes = buf.getvalue()
            ns_data = self._NSData.alloc().initWithBytes_length_(png_bytes, len(png_bytes))
            ns_image = self._NSImage.alloc().initWithData_(ns_data)
            frames.append(ns_image)
        return frames

    def _load_frames_tk(self, path):
        """Load GIF frames as tk.PhotoImage objects."""
        frames = []
        i = 0
        while True:
            try:
                frames.append(tk.PhotoImage(file=path, format=f"gif -index {i}"))
                i += 1
            except tk.TclError:
                break
        return frames

    def _frame_size(self, frame):
        if self._is_macos:
            sz = frame.size()
            return int(sz.width), int(sz.height)
        return frame.width(), frame.height()

    def _set_frame(self, index):
        """Display frame at *index* from current_frames and update w/h."""
        frame = self.current_frames[index]
        if self._is_macos:
            self._ns_image_view.setImage_(frame)
        else:
            self.label.configure(image=frame)
            self.label.image = frame
        self.w, self.h = self._frame_size(frame)

    def _move_window(self):
        """Position the display window at (self.x, self.y) with size (self.w, self.h)."""
        if self._is_macos:
            ns_y = self._screen_h - self.y - self.h
            self._ns_window.setFrame_display_(
                self._NSMakeRect(self.x, ns_y, self.w, self.h), True,
            )
            self._ns_image_view.setFrame_(self._NSMakeRect(0, 0, self.w, self.h))
        else:
            self.window.geometry(
                f"{self.w}x{self.h}+{int(self.x)}+{int(self.y)}"
            )

    def _quit(self):
        if self._is_macos:
            self._ns_window.close()
        self.window.destroy()

    def show_menu(self, event):
        self.menu.tk_popup(event.x_root, event.y_root)

    def toggle_pause(self):
        self.paused = not self.paused

    def start_drag(self, event):
        self._drag = (event.x, event.y)
        self.direction = 1 if event.x >= self.w // 2 else -1
        self.enter_state("drag", force=True)

    def on_drag(self, event):
        if self._drag is None:
            return
        dx = event.x - self._drag[0]
        dy = event.y - self._drag[1]
        self.x += dx
        self.y += dy
        self._move_window()

    def end_drag(self, event):
        self._drag = None
        self.swing_phase = 0
        self.swinging = True
        self.enter_state("walk")
        self.do_swing()

    def start_drag_native(self, local_x, local_y):
        self._drag = (local_x, local_y)
        self.direction = 1 if local_x >= self.w // 2 else -1
        self.enter_state("drag", force=True)

    def on_drag_native(self, event):
        if self._drag is None:
            return
        dx = event.deltaX()
        dy = event.deltaY()
        self.x += dx
        self.y += dy
        self._move_window()

    def end_drag_native(self, local_x, local_y):
        self._drag = None
        self.swing_phase = 0
        self.swinging = True
        self.enter_state("walk")
        self.do_swing()

    def do_swing(self):
        if not hasattr(self, "swinging") or not self.swinging:
            return

        yoff = int(5 * (1 - abs(self.swing_phase - 5) / 5))
        xamp = 3
        xdir = 1 if self.direction >= 0 else -1
        xoff = int(xamp * (1 - abs(self.swing_phase - 5) / 5)) * xdir

        # Temporary position offset for the swing
        orig_x, orig_y = self.x, self.y
        self.x += xoff
        self.y -= yoff
        self._move_window()
        self.x, self.y = orig_x, orig_y

        self.swing_phase += 1

        if self.swing_phase > 10:
            self.swinging = False
            self._move_window()
            return

        self.window.after(30, self.do_swing)

    def pick_frames_by_state_dir(self, state):
        if state == "walk":
            return self.frames["walk_right"] if self.direction >= 0 else self.frames["walk_left"]

        if state == "fire":
            if self.direction >= 0:
                return (
                    self.frames["fire_right"]
                    if self.frames["fire_right"]
                    else (self.frames["fire"] if self.frames["fire"] else self.frames["walk_right"])
                )
            return (
                self.frames["fire_left"]
                if self.frames["fire_left"]
                else (self.frames["fire"] if self.frames["fire"] else self.frames["walk_left"])
            )

        if state == "idle":
            return self.frames["idle_right"] if self.direction >= 0 else self.frames["idle_left"]

        if state == "drag":
            if self.direction >= 0:
                return (
                    self.frames["sway_right"]
                    if self.frames["sway_right"]
                    else (self.frames["sway"] if self.frames["sway"] else self.frames["idle_right"])
                )
            return (
                self.frames["sway_left"]
                if self.frames["sway_left"]
                else (self.frames["sway"] if self.frames["sway"] else self.frames["idle_left"])
            )

        if state == "descend":
            return self.frames["descend"]

        return self.frames["walk_right"]

    def enter_state(self, new_state, force=False):
        prev_state = self.state
        if new_state == self.state and not force:
            return

        self.state = new_state
        self.frame_index = 0
        self.current_frames = self.pick_frames_by_state_dir(new_state)
        self._set_frame(self.frame_index)
        self._move_window()

        if new_state == "fire":
            self.y -= 5
            self.x -= self.direction * 8
            self._move_window()

        if new_state == "walk" and prev_state == "fire":
            self.y += 5
            self.x += self.direction * 8
            self._move_window()

        if new_state == "descend":
            self.vy = 0.0

    def update(self):
        now = time.perf_counter()
        dt = now - self._last_t
        self._last_t = now

        if not self.paused:
            # Gravity
            if self.state != "drag":
                if self.y < self.ground_y:
                    self.vy += self.gravity * dt
                    self.y += self.vy * dt

                    if self.y >= self.ground_y:
                        self.y = self.ground_y
                        self.vy = 0.0

                        if not self.has_landed_once:
                            self.has_landed_once = True
                            self.descend_until = now + self.DESCEND_DURATION
                            self.enter_state("descend", force=True)
                else:
                    if self.state == "descend":
                        if now >= (self.descend_until or now):
                            self.enter_state("walk")

            # State priority: drag > descend > idle > fire
            if self.state not in ("drag", "descend"):
                grounded = self.y >= self.ground_y - 1

                if self.state == "walk" and grounded and now >= self.next_idle_time:
                    self.enter_state("idle")
                    self.idle_until = now + self.IDLE_DURATION

                    if self.next_fire_time < self.idle_until + 0.1:
                        self.next_fire_time = self.idle_until + 0.1

                elif self.state == "idle":
                    if now >= (self.idle_until or now):
                        self.enter_state("walk")

                        if self.next_fire_time < now + 0.2:
                            self.next_fire_time = now + 0.2

                        self.next_idle_time = now + random.uniform(self.IDLE_MIN, self.IDLE_MAX)

                else:
                    if (
                        self.state != "fire"
                        and now >= self.next_fire_time
                        and (self.frames["fire_right"] or self.frames["fire_left"] or self.frames["fire"])
                    ):
                        self.enter_state("fire")
                        self.fire_until = now + self.FIRE_DURATION

                    elif self.state == "fire" and now >= (self.fire_until or now):
                        self.enter_state("walk")
                        self.next_fire_time = now + random.uniform(self.FIRE_MIN, self.FIRE_MAX)

            # Animation
            if self.state == "walk":
                st = "walk"
            elif self.state == "fire":
                st = "fire"
            elif self.state == "drag":
                st = "sway"
            elif self.state == "descend":
                st = "descend"
            else:
                st = "idle"

            target_ft = self.frame_time[st]
            self._acc += dt

            while self._acc >= target_ft:
                self._acc -= target_ft
                self.frame_index = (self.frame_index + 1) % len(self.current_frames)
                self._set_frame(self.frame_index)

            # Horizontal movement
            if self.state == "walk" and self.y >= self.ground_y:
                self.x += self.speed * self.direction

                if now >= self.next_turn_time:
                    self.direction *= -1
                    self.enter_state("walk", force=True)
                    self.next_turn_time = now + random.uniform(self.TURN_MIN, self.TURN_MAX)

                if self.x <= self.screen_left:
                    self.x = self.screen_left
                    self.direction = 1
                    self.enter_state("walk", force=True)
                    self.next_turn_time = now + random.uniform(self.TURN_MIN, self.TURN_MAX)

                if self.x + self.w >= self.screen_right:
                    self.x = self.screen_right - self.w
                    self.direction = -1
                    self.enter_state("walk", force=True)
                    self.next_turn_time = now + random.uniform(self.TURN_MIN, self.TURN_MAX)

            self._move_window()

        self.window.after(10, self.update)


if __name__ == "__main__":
    try:
        Pet()
    except Exception as e:
        print("Error:", e, file=sys.stderr)
        raise
