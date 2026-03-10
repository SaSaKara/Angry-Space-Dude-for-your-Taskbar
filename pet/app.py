import os
import random
import sys
import time
import tkinter as tk

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

        # === WINDOW ===
        self.window = tk.Tk()
        self.window.overrideredirect(True)
        self.window.attributes("-topmost", True)
        self.window.config(highlightbackground="black")
        self.window.wm_attributes("-transparentcolor", "black")
        self.window.bind("<Escape>", lambda e: self.window.destroy())

        # Window/taskbar icon
        if os.path.exists(icon_path):
            try:
                self.window.iconbitmap(icon_path)
            except Exception:
                pass

        # --- Right-click menu ---
        self.menu = tk.Menu(self.window, tearoff=0)
        self.menu.add_command(label="Pause/Resume (Space)", command=self.toggle_pause)
        self.menu.add_separator()
        self.menu.add_command(label="Exit", command=self.window.destroy)

        # === Load animations from assets folder ===
        def load_frames(filename):
            path = os.path.join(assets_dir, filename)
            frames = []
            i = 0

            if not os.path.exists(path):
                return frames

            while True:
                try:
                    frames.append(tk.PhotoImage(file=path, format=f"gif -index {i}"))
                    i += 1
                except tk.TclError:
                    break

            return frames

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

        # Visual
        self.label = tk.Label(self.window, bd=0, bg="black")
        self.label.pack()
        self.label.bind("<Button-3>", self.show_menu)

        # Drag & drop
        self._drag = None
        self.label.bind("<Button-1>", self.start_drag)
        self.label.bind("<B1-Motion>", self.on_drag)
        self.label.bind("<ButtonRelease-1>", self.end_drag)

        # Work area and ground
        l, t, r, b = get_work_area()
        self.screen_left = l
        self.screen_top = t
        self.screen_right = r
        self.screen_bottom = b

        # Initial image
        self.current_frames = self.frames["walk_right"]
        self.img = self.current_frames[self.frame_index]
        self.label.configure(image=self.img)
        self.label.image = self.img
        self.w = self.img.width()
        self.h = self.img.height()

        # Spawn from above
        self.x = self.screen_left
        self.y = self.screen_top - self.h
        self.window.geometry(f"{self.w}x{self.h}+{int(self.x)}+{int(self.y)}")

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

        # Shortcuts
        self.window.bind("<space>", lambda e: self.toggle_pause())

        # Loop
        self.update()
        self.window.mainloop()

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
        self.window.geometry(f"{self.w}x{self.h}+{int(self.x)}+{int(self.y)}")

    def end_drag(self, event):
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

        self.window.geometry(
            f"{self.w}x{self.h}+{int(self.x + xoff)}+{int(self.y - yoff)}"
        )
        self.swing_phase += 1

        if self.swing_phase > 10:
            self.swinging = False
            self.window.geometry(f"{self.w}x{self.h}+{int(self.x)}+{int(self.y)}")
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

        self.img = self.current_frames[self.frame_index]
        self.label.configure(image=self.img)
        self.label.image = self.img
        self.w = self.img.width()
        self.h = self.img.height()
        self.window.geometry(f"{self.w}x{self.h}+{int(self.x)}+{int(self.y)}")

        if new_state == "fire":
            self.y -= 5
            self.x -= self.direction * 8
            self.window.geometry(f"{self.w}x{self.h}+{int(self.x)}+{int(self.y)}")

        if new_state == "walk" and prev_state == "fire":
            self.y += 5
            self.x += self.direction * 8
            self.window.geometry(f"{self.w}x{self.h}+{int(self.x)}+{int(self.y)}")

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
                self.img = self.current_frames[self.frame_index]
                self.label.configure(image=self.img)
                self.label.image = self.img

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

            self.window.geometry(f"{self.w}x{self.h}+{int(self.x)}+{int(self.y)}")

        self.window.after(10, self.update)


if __name__ == "__main__":
    try:
        Pet()
    except Exception as e:
        print("Error:", e, file=sys.stderr)
        raise