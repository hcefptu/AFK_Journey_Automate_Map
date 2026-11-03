import ctypes
import json
import math
import os
import sys
import time
import unicodedata
from dataclasses import dataclass, field

try:
    ctypes.windll.shcore.SetProcessDpiAwareness(2)
except Exception:
    try:
        ctypes.windll.user32.SetProcessDPIAware()
    except Exception:
        pass

import cv2
import keyboard
import mss
import numpy as np
import pyautogui
import pygetwindow as gw
import win32gui

pyautogui.PAUSE = 0.0

BASE_DIR = os.path.dirname(os.path.abspath(__file__))

TEMPLATE_DIR = os.path.join(BASE_DIR, "templates")
DEBUG_DIR = os.path.join(BASE_DIR, "debug")
SHOTS_DIR = os.path.join(BASE_DIR, "shots")
GAME_WINDOW_TITLE = "AFK Journey"
LOOP_DELAY = 0.05
SCALES = tuple(round(0.05 * (1.12 ** i), 3) for i in range(35))
MIN_TPL_PX = 18

CROPS = {
    "theo_doi_1.png": (0.28, 0.25, 0.72, 0.62),
    "theo_doi_2.png": (0.30, 0.14, 0.70, 0.58),
    "theo_doi_3.png": (0.25, 0.14, 0.75, 0.60),
}
SKIP_BUTTON_REL = (0.777, 0.944)
HUD_FILE = "hud_joystick.png"
HUD_ROI = (0.42, 0.68, 0.16, 0.19)
TAP_CONTINUE_REL = (0.50, 0.936)
TAP_IDLE = 3.0
SCALE_CACHE = os.path.join(TEMPLATE_DIR, "scales.json")

try:
    with open(SCALE_CACHE, "r", encoding="utf-8") as _f:
        _best_scale = json.load(_f)
except Exception:
    _best_scale = {}

def read_gray(path):
    try:
        data = np.fromfile(path, dtype=np.uint8)
        return cv2.imdecode(data, cv2.IMREAD_GRAYSCALE) if data.size else None
    except Exception:
        return None

def write_image(path, img):
    ok, buf = cv2.imencode(os.path.splitext(path)[1] or ".png", img)
    if ok:
        buf.tofile(path)
    return ok

def save_scales():
    try:
        with open(SCALE_CACHE, "w", encoding="utf-8") as f:
            json.dump(_best_scale, f, indent=1)
    except Exception:
        pass

BLACK_SCREEN_THRESHOLD = 15
BLACK_SCREEN_WAIT = 1.5
FOLLOW_COOLDOWN = 2.5
FOLLOW_REL = (0.575, 0.73)
MOVE_DIFF = 6.0

HUD_THRESHOLD = 0.45
FOLLOW_THRESHOLD = 0.55
QUEST_MARKER_THRESHOLD = 0.65

UNKNOWN_TIMEOUT = 15.0
BATTLE_GRACE = 90.0
MAX_NUDGES = 4
ALARM_EVERY = 8.0

MOTION_INTERVAL = 0.6
MOVE_PX = 1.5
STUCK_PRESSES = 1
JOY_REL = (0.50, 0.776)
JOY_DRAG_PX = 30
NUDGE_HOLD = 0.6
NUDGE_MODE = "mouse"
NUDGE_DIRS = [(0, 1), (-1, 0), (1, 0), (0, -1), (1, 1), (-1, 1), (1, -1), (-1, -1)]

HOLD_MODE = "mouse"
HOLD_DURATION = 5.5
HOLD_ROI_WIDE = (0.35, 0.55, 0.30, 0.25)
HOLD_HSV_LO = np.array([12, 120, 180])
HOLD_HSV_HI = np.array([32, 255, 255])
HOLD_AREA_MIN = 1500
HOLD_AREA_MAX = 6000
HOLD_R_MIN = 20
HOLD_R_MAX = 55
HOLD_FILL_MIN = 0.65
HOLD_FILL_MAX = 0.95
HOLD_KERNEL = np.ones((5, 5), np.uint8)

@dataclass
class Rule:
    name: str
    files: list
    threshold: float = 0.80
    roi: tuple = None
    after: float = 1.0
    cooldown: float = 0.0
    antirepeat: bool = True
    last: float = field(default=0.0, repr=False)
    last_pos: tuple = field(default=None, repr=False)
    repeat: int = field(default=0, repr=False)
    blocked_until: float = field(default=0.0, repr=False)

RULES = [
    Rule("Tap to close / continue", ["nhan_de_dong.png", "nhan_de_tiep_tuc.png"], 0.75, roi=(0.20, 0.88, 0.60, 0.12), after=0.8),
    Rule("Green check (confirm)", ["tick_xanh.png"], 0.85, roi=(0.50, 0.55, 0.20, 0.30), after=0.8),
    Rule("Skip", ["bo_qua_1.png", "bo_qua_2.png"], 0.88, roi=(0.6, 0.8, 0.4, 0.2), after=0.8),
    Rule("Battle", ["chien_dau.png"], 0.75, roi=(0.20, 0.82, 0.60, 0.18), after=0.8),
    Rule("Dialogue", ["hoi_thoai_1.png", "icon_hoi_thoai.png"], 0.75, roi=(0.30, 0.55, 0.50, 0.35), after=0.8),
]

_template_cache = {}
_scaled_tpl_cache = {}
_sct = mss.MSS()

def load_template(name):
    if name not in _template_cache:
        path = os.path.join(TEMPLATE_DIR, name)
        img = read_gray(path) if os.path.exists(path) else None
        if img is not None and name in CROPS:
            ih, iw = img.shape
            x0, y0, x1, y1 = CROPS[name]
            img = img[int(ih * y0):int(ih * y1), int(iw * x0):int(iw * x1)]
        _template_cache[name] = img
    return _template_cache[name]

def get_scaled_tpl(tpl_name, scale):
    key = (tpl_name, round(scale, 3))
    if key in _scaled_tpl_cache:
        return _scaled_tpl_cache[key]
    tpl = load_template(tpl_name)
    if tpl is None:
        _scaled_tpl_cache[key] = None
        return None
    w = int(tpl.shape[1] * scale)
    h = int(tpl.shape[0] * scale)
    if w < MIN_TPL_PX or h < MIN_TPL_PX:
        _scaled_tpl_cache[key] = None
        return None
    interp = cv2.INTER_AREA if scale < 1 else cv2.INTER_LINEAR
    result = cv2.resize(tpl, (w, h), interpolation=interp)
    _scaled_tpl_cache[key] = result
    return result

_win_cache = {"info": None, "time": 0}
def get_game_window_info():
    now = time.time()
    if _win_cache["info"] and now - _win_cache["time"] < 2.0:
        return _win_cache["info"]
    try:
        wins = gw.getWindowsWithTitle(GAME_WINDOW_TITLE)
        if not wins:
            _win_cache["info"] = None
            return None, None, None, None, None
        win = wins[0]
        if win.isMinimized:
            win.restore()
            time.sleep(0.3)
        if not win.isActive:
            try:
                win.activate()
                time.sleep(0.15)
            except Exception:
                pass
        hwnd = win._hWnd
        rect = win32gui.GetClientRect(hwnd)
        pt = win32gui.ClientToScreen(hwnd, (0, 0))
        result = (win, hwnd, pt[0], pt[1], (rect[2], rect[3]))
        _win_cache["info"] = result
        _win_cache["time"] = now
        return result
    except Exception:
        return None, None, None, None, None

def grab(client_x, client_y, client_w, client_h):
    monitor = {"top": client_y, "left": client_x, "width": client_w, "height": client_h}
    img = np.array(_sct.grab(monitor))
    bgr = cv2.cvtColor(img, cv2.COLOR_BGRA2BGR)
    gray = cv2.cvtColor(bgr, cv2.COLOR_BGR2GRAY)
    return gray, bgr

def click_fast(x, y, hold=0.04):
    pyautogui.moveTo(x, y, duration=0)
    pyautogui.mouseDown()
    time.sleep(hold)
    pyautogui.mouseUp()

def match(gray, tpl_name, threshold, roi):
    tpl = load_template(tpl_name)
    if tpl is None: return 0.0, None, None, None

    H, W = gray.shape
    if roi:
        rx, ry, rw, rh = int(roi[0]*W), int(roi[1]*H), int(roi[2]*W), int(roi[3]*H)
        area = gray[ry:ry+rh, rx:rx+rw]
        ox, oy = rx, ry
    else:
        area = gray
        ox, oy = 0, 0

    cached_scale = _best_scale.get(tpl_name)
    if cached_scale is not None:
        scaled = get_scaled_tpl(tpl_name, cached_scale)
        if scaled is None: return 0.0, None, None, None
        sh, sw = scaled.shape
        if sh > area.shape[0] or sw > area.shape[1]: return 0.0, None, None, None
        res = cv2.matchTemplate(area, scaled, cv2.TM_CCOEFF_NORMED)
        _, mx, _, loc = cv2.minMaxLoc(res)
        if mx >= threshold:
            return mx, ox + loc[0] + sw//2, oy + loc[1] + sh//2, (loc[0]+ox, loc[1]+oy, sw, sh)
        return mx, None, None, None

    if tpl.shape[1] > area.shape[1] or tpl.shape[0] > area.shape[0]:
        ratio = min(area.shape[1] / tpl.shape[1], area.shape[0] / tpl.shape[0]) * 0.95
        scales_to_try = [round(ratio * f, 3) for f in (0.7, 0.85, 1.0)]
    else:
        scales_to_try = SCALES

    best_mx = 0.0
    best_result = None
    best_scale = None
    for s in scales_to_try:
        scaled = get_scaled_tpl(tpl_name, s)
        if scaled is None: continue
        sh, sw = scaled.shape
        if sh > area.shape[0] or sw > area.shape[1]: continue
        res = cv2.matchTemplate(area, scaled, cv2.TM_CCOEFF_NORMED)
        _, mx, _, loc = cv2.minMaxLoc(res)
        if mx > best_mx:
            best_mx = mx
            best_result = (ox + loc[0] + sw//2, oy + loc[1] + sh//2, (loc[0]+ox, loc[1]+oy, sw, sh))
            best_scale = s

    if best_scale is not None and best_mx >= 0.85:
        _best_scale[tpl_name] = best_scale
        save_scales()

    if best_mx >= threshold and best_result:
        return best_mx, best_result[0], best_result[1], best_result[2]
    return best_mx, None, None, None

def check_white_f_below(bgr, cx, cy, r):
    H, W = bgr.shape[:2]
    cx, cy, r = int(round(cx)), int(round(cy)), int(round(r))
    y1 = min(cy + r, H - 1)
    y2 = min(cy + r + 30, H)
    x1 = max(cx - r, 0)
    x2 = min(cx + r, W)
    if y1 >= y2 or x1 >= x2: return False
    region = bgr[y1:y2, x1:x2]
    if region.size == 0: return False
    white_mask = (region[:,:,0] > 200) & (region[:,:,1] > 200) & (region[:,:,2] > 200)
    return np.sum(white_mask) > 30

def find_hold_button(bgr):
    H, W = bgr.shape[:2]
    rx, ry, rw, rh = int(HOLD_ROI_WIDE[0]*W), int(HOLD_ROI_WIDE[1]*H), int(HOLD_ROI_WIDE[2]*W), int(HOLD_ROI_WIDE[3]*H)
    roi = bgr[ry:ry+rh, rx:rx+rw]

    hsv = cv2.cvtColor(roi, cv2.COLOR_BGR2HSV)
    mask = cv2.inRange(hsv, HOLD_HSV_LO, HOLD_HSV_HI)
    mask = cv2.morphologyEx(mask, cv2.MORPH_CLOSE, HOLD_KERNEL)

    contours, _ = cv2.findContours(mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    if not contours: return None, None, None

    c = max(contours, key=cv2.contourArea)
    area = cv2.contourArea(c)
    (x, y), r = cv2.minEnclosingCircle(c)
    fill = area / (np.pi * r * r) if r > 0 else 0

    if not ((HOLD_AREA_MIN <= area <= HOLD_AREA_MAX) and (HOLD_R_MIN <= r <= HOLD_R_MAX) and (HOLD_FILL_MIN <= fill <= HOLD_FILL_MAX)):
        return None, None, None

    gx, gy, r = rx + int(x), ry + int(y), int(round(r))
    if not check_white_f_below(bgr, gx, gy, r):
        return None, None, None
    return gx, gy, r

_MOTION_SIZE = (448, 200)
_MOTION_WIN = cv2.createHanningWindow(_MOTION_SIZE, cv2.CV_32F)

def motion_frame(gray):
    H, W = gray.shape
    area = gray[int(H * 0.14):int(H * 0.66), int(W * 0.12):int(W * 0.82)]
    return cv2.resize(area, _MOTION_SIZE, interpolation=cv2.INTER_AREA).astype(np.float32)

def new_motion():
    return {"ref": None, "t": 0.0, "moved": False, "max": 0.0}

def update_motion(m, gray):
    now = time.time()
    cur = motion_frame(gray)
    if m["ref"] is None or now - m["t"] > 3.5:
        m["ref"], m["t"] = cur, now
        return
    if now - m["t"] >= MOTION_INTERVAL:
        (dx, dy), _resp = cv2.phaseCorrelate(m["ref"], cur, _MOTION_WIN)
        mag = math.hypot(dx, dy)
        m["max"] = max(m["max"], mag)
        if mag >= MOVE_PX:
            m["moved"] = True
        m["ref"], m["t"] = cur, now

def reset_motion(m):
    m["ref"] = None
    m["moved"] = False
    m["max"] = 0.0

def skip_circle_visible(gray):
    H, W = gray.shape
    cx, cy, r = int(W * 0.7745), int(H * 0.9427), 17
    inner = gray[cy - r:cy + r, cx - r:cx + r]
    return inner.size > 0 and float((inner > 200).mean()) >= 0.45

def nudge_joystick(client_x, client_y, cw, ch, idx):
    dx, dy = NUDGE_DIRS[idx % len(NUDGE_DIRS)]
    n = math.hypot(dx, dy)
    ux, uy = dx / n, dy / n
    name = {(0, 1): "down", (-1, 0): "left", (1, 0): "right", (0, -1): "up"}.get((dx, dy), f"diagonal {dx},{dy}")
    print(f"[UNSTICK] Character is not moving. Nudging the joystick {name} ({NUDGE_MODE}), then pressing Follow again.", flush=True)
    if NUDGE_MODE == "keys":
        keys = []
        if dx < 0: keys.append('a')
        if dx > 0: keys.append('d')
        if dy < 0: keys.append('w')
        if dy > 0: keys.append('s')
        try:
            for k in keys: keyboard.press(k)
            time.sleep(NUDGE_HOLD)
        finally:
            for k in keys: keyboard.release(k)
        return
    x0 = client_x + int(cw * JOY_REL[0])
    y0 = client_y + int(ch * JOY_REL[1])
    x1 = x0 + int(ux * JOY_DRAG_PX)
    y1 = y0 + int(uy * JOY_DRAG_PX)
    try:
        pyautogui.moveTo(x0, y0, duration=0)
        pyautogui.mouseDown()
        pyautogui.moveTo(x1, y1, duration=0.15)
        time.sleep(NUDGE_HOLD)
    finally:
        pyautogui.mouseUp()

def alarm_beep():
    try:
        import winsound
        for f in (880, 1175, 1568):
            winsound.Beep(f, 180)
    except Exception:
        print("\a", end="", flush=True)

def save_unknown(bgr, tag):
    d = os.path.join(DEBUG_DIR, "unknown", time.strftime("%Y-%m-%d"))
    os.makedirs(d, exist_ok=True)
    path = os.path.join(d, f"{int(time.time())}_{tag}.png")
    write_image(path, bgr)
    return path

def sanitize_filename(text):
    text = unicodedata.normalize('NFKD', text).encode('ASCII', 'ignore').decode('utf-8')
    return text.replace(" ", "_")

def save_debug(bgr, tag, cx, cy, rect):
    date_str = time.strftime("%Y-%m-%d")
    debug_dir = os.path.join(DEBUG_DIR, date_str)
    os.makedirs(debug_dir, exist_ok=True)
    img = bgr.copy()
    if rect:
        x1, y1, w, h = rect
        cv2.rectangle(img, (x1, y1), (x1 + w, y1 + h), (0, 255, 0), 2)
    if cx and cy:
        cv2.circle(img, (cx, cy), 8, (0, 0, 255), -1)
        cv2.putText(img, sanitize_filename(tag), (cx + 10, cy), cv2.FONT_HERSHEY_SIMPLEX, 0.6, (0, 0, 255), 2)
    write_image(os.path.join(debug_dir, f"{int(time.time())}_{sanitize_filename(tag)}.png"), img)

def do_hold(client_x, client_y, cx, cy):
    print(f"[HOLD] Holding at ({cx}, {cy}) for {HOLD_DURATION} seconds...", flush=True)
    real_x, real_y = client_x + cx, client_y + cy
    t0 = time.time()
    try:
        if HOLD_MODE == "mouse":
            pyautogui.moveTo(real_x, real_y, duration=0)
            pyautogui.mouseDown()
        else:
            keyboard.press('f')
        while time.time() - t0 < HOLD_DURATION:
            if keyboard.is_pressed("F8"):
                print("[HOLD] F8 detected, releasing.", flush=True)
                break
            time.sleep(0.1)
    finally:
        if HOLD_MODE == "mouse":
            pyautogui.mouseUp()
        else:
            keyboard.release('f')
        print(f"[HOLD] Released. Actual hold time: {time.time()-t0:.2f}s", flush=True)

def walk_to_quest_marker(gray, bgr, cw, ch):
    score, tx, ty, rect = match(gray, "quest_marker.png", QUEST_MARKER_THRESHOLD, None)
    if tx is None:
        return False

    print(f"[PATH] Target seen at ({tx}, {ty}). Walking...", flush=True)
    cx, cy = cw // 2, ch // 2
    dx = tx - cx
    dy = ty - cy
    DEADZONE = 50

    moved = False
    if dy < -DEADZONE:
        keyboard.press('w'); moved = True
    elif dy > DEADZONE:
        keyboard.press('s'); moved = True
    if dx < -DEADZONE:
        keyboard.press('a'); moved = True
    elif dx > DEADZONE:
        keyboard.press('d'); moved = True

    if moved:
        time.sleep(0.4)
        keyboard.release('w'); keyboard.release('a')
        keyboard.release('s'); keyboard.release('d')
        time.sleep(0.1)
        return True
    return False

def looks_like_choice(gray):
    H, W = gray.shape
    top_area = gray[int(H * 0.10):int(H * 0.30), int(W * 0.35):int(W * 0.65)]
    if top_area.mean() > 180:
        return False
    box = gray[int(H * 0.70):int(H * 0.90), int(W * 0.30):int(W * 0.70)]
    bar = gray[int(H * 0.965):int(H * 0.99), int(W * 0.10):int(W * 0.90)]
    return box.mean() > 180 and bar.mean() < 60

def looks_like_dialogue(gray):
    H, W = gray.shape
    box = gray[int(H * 0.75):int(H * 0.88), int(W * 0.28):int(W * 0.70)]
    bar = gray[int(H * 0.965):int(H * 0.99), int(W * 0.10):int(W * 0.90)]
    return box.mean() > 175 and bar.mean() < 45

def main():
    shot_mode = "--shot" in sys.argv
    debug_mode = "--debug" in sys.argv

    if shot_mode:
        print("Capturing the game window in 3 seconds...", flush=True)
        time.sleep(3)
        win, hwnd, cx, cy, (cw, ch) = get_game_window_info()
        if win is None:
            print("Game window not found.", flush=True)
            return
        os.makedirs(SHOTS_DIR, exist_ok=True)
        _, bgr = grab(cx, cy, cw, ch)
        path = os.path.join(SHOTS_DIR, f"shot_{int(time.time())}.png")
        write_image(path, bgr)
        print(f"Saved {path} ({bgr.shape[1]}x{bgr.shape[0]}).", flush=True)
        return

    print("=" * 44, flush=True)
    print(" AFK JOURNEY BOT | F8 = quit | F9 = pause / resume", flush=True)
    print("=" * 44, flush=True)

    win, hwnd, client_x, client_y, (cw, ch) = get_game_window_info()
    if win:
        print(f"[INFO] Connected to the game window. Client area: {cw}x{ch}", flush=True)
        print(f"[INFO] HUD threshold = {HUD_THRESHOLD}, Follow threshold = {FOLLOW_THRESHOLD}", flush=True)

    last_action = time.time()
    paused = False
    loop = 0
    follow_rule = Rule("Follow", ["theo_doi_1.png", "theo_doi_2.png", "theo_doi_3.png"], FOLLOW_THRESHOLD, roi=(0.52, 0.66, 0.12, 0.16), after=1.0, cooldown=FOLLOW_COOLDOWN, antirepeat=False)

    needed = sorted({f for r in RULES for f in r.files} | set(follow_rule.files))
    optional = ["in_battle.png", "gift_f_button.png", "quest_marker.png", HUD_FILE]
    missing = [f for f in needed if not os.path.isfile(os.path.join(TEMPLATE_DIR, f))]
    missing_optional = [f for f in optional if not os.path.isfile(os.path.join(TEMPLATE_DIR, f))]
    if missing:
        print("[WARNING] Missing template images (the matching rules will not work): " + ", ".join(missing), flush=True)
    if missing_optional:
        print("[INFO] Optional template images not found: " + ", ".join(missing_optional), flush=True)

    hold_confirm_frames = 0
    stuck_frames = 0
    last_marker_pos = None
    marker_stuck_count = 0
    motion = new_motion()
    pressed_once = False
    still_count = 0
    nudge_idx = 0
    nudge_streak = 0
    unknown_since = None
    battle_grace_until = 0.0
    pause_reason = None
    alarm_next = 0.0

    def trigger_pause(reason, frame):
        nonlocal paused, pause_reason, alarm_next
        paused = True
        pause_reason = reason
        alarm_next = 0.0
        path = save_unknown(frame, "pause")
        print("=" * 60, flush=True)
        print(f"[WAITING FOR YOU] {reason}.", flush=True)
        print("          The bot has STOPPED clicking. Handle it in the game yourself, then press F9 to resume (F8 = quit).", flush=True)
        print(f"          Screenshot taken when it stopped: {path}", flush=True)
        print("=" * 60, flush=True)

    try:
        while True:
            if keyboard.is_pressed("F8"):
                print("[INFO] Bot stopped (F8).", flush=True)
                break
            if keyboard.is_pressed("F9"):
                paused = not paused
                if paused:
                    pause_reason = None
                else:
                    pause_reason = None
                    unknown_since = None
                    last_action = time.time()
                    stuck_frames = 0
                    still_count = 0
                    nudge_streak = 0
                    pressed_once = False
                    reset_motion(motion)
                print("[INFO] Paused." if paused else "[INFO] Resumed.", flush=True)
                time.sleep(0.6)
            if paused:
                if pause_reason and time.time() >= alarm_next:
                    alarm_beep()
                    alarm_next = time.time() + ALARM_EVERY
                time.sleep(0.2)
                continue

            win, hwnd, client_x, client_y, (cw, ch) = get_game_window_info()
            if win is None:
                time.sleep(1)
                continue

            loop += 1
            gray, bgr = grab(client_x, client_y, cw, ch)

            if gray.mean() < BLACK_SCREEN_THRESHOLD:
                skip_xy = None
                for f in ("bo_qua_2.png", "bo_qua_1.png"):
                    sc, sx, sy, _r = match(gray, f, 0.85, (0.6, 0.8, 0.4, 0.2))
                    if sx is not None:
                        print(f"[CLICK] Skip (dark screen / cutscene) {f} matched {sc:.2f}", flush=True)
                        skip_xy = (sx, sy)
                        break
                if skip_xy is None and skip_circle_visible(gray):
                    print("[CLICK] Skip (dark screen / cutscene, detected by round button shape)", flush=True)
                    skip_xy = (int(cw * SKIP_BUTTON_REL[0]), int(ch * SKIP_BUTTON_REL[1]))
                if skip_xy is not None:
                    if debug_mode: save_debug(bgr, "Cutscene skip", skip_xy[0], skip_xy[1], None)
                    click_fast(client_x + skip_xy[0], client_y + skip_xy[1])
                    last_action = time.time()
                    unknown_since = None
                    time.sleep(0.8)
                    continue
                time.sleep(BLACK_SCREEN_WAIT)
                last_action = time.time()
                unknown_since = None
                continue

            g_score, gx, gy, g_rect = match(gray, "gift_f_button.png", 0.75, (0.30, 0.40, 0.40, 0.40))
            if gx is not None:
                print(f"[CLICK] Interact button (gift F) matched {g_score:.2f}. Pressing F...", flush=True)
                keyboard.press_and_release('f')
                last_action = time.time()
                unknown_since = None
                stuck_frames = 0
                time.sleep(1.5)
                continue

            hcx, hcy, hr = find_hold_button(bgr)
            if hcx is not None:
                hold_confirm_frames += 1
                if hold_confirm_frames >= 2:
                    print(f"[HOLD] Hold button detected at ({hcx}, {hcy}).", flush=True)
                    if debug_mode: save_debug(bgr, "Hold", hcx, hcy, None)
                    do_hold(client_x, client_y, hcx, hcy)
                    time.sleep(0.8)
                    hold_confirm_frames = 0
                    last_action = time.time()
                    unknown_since = None
                    stuck_frames = 0
                    continue
                else:
                    time.sleep(0.1)
                    continue
            else:
                hold_confirm_frames = 0

            acted = False
            for rule in RULES:
                now = time.time()
                if now - rule.last < rule.cooldown or now < rule.blocked_until: continue
                for f in rule.files:
                    score, cx, cy, rect = match(gray, f, rule.threshold, rule.roi)
                    if cx is not None:
                        print(f"[CLICK] {rule.name} matched {score:.2f}", flush=True)
                        if debug_mode: save_debug(bgr, rule.name, cx, cy, rect)
                        click_fast(client_x + cx, client_y + cy)
                        rule.last = time.time()
                        if rule.name == "Battle":
                            battle_grace_until = time.time() + BATTLE_GRACE
                        time.sleep(rule.after)
                        acted = True
                        break
                if acted: break
            if acted:
                stuck_frames = 0
                unknown_since = None
                continue

            if looks_like_choice(gray):
                print("[CLICK] Choosing the dialogue option (layout)", flush=True)
                click_fast(client_x + int(cw * 0.50), client_y + int(ch * 0.73))
                last_action = time.time()
                unknown_since = None
                stuck_frames = 0
                time.sleep(1.5)
                continue
            if looks_like_dialogue(gray):
                print("[CLICK] Skip (layout)", flush=True)
                click_fast(client_x + int(cw * SKIP_BUTTON_REL[0]), client_y + int(ch * SKIP_BUTTON_REL[1]))
                last_action = time.time()
                unknown_since = None
                stuck_frames = 0
                time.sleep(1.5)
                continue

            on_map = False
            hud_score, hx_, _hy, _rect = match(gray, HUD_FILE, HUD_THRESHOLD, HUD_ROI)
            if hx_ is not None:
                on_map = True
            else:
                for f in follow_rule.files:
                    s, _, _, _ = match(gray, f, FOLLOW_THRESHOLD, follow_rule.roi)
                    if s >= FOLLOW_THRESHOLD:
                        on_map = True
                        break

            if on_map:
                stuck_frames = 0
                unknown_since = None
                now = time.time()
                update_motion(motion, gray)

                m_score, tx, ty, m_rect = match(gray, "quest_marker.png", QUEST_MARKER_THRESHOLD, None)
                if m_score >= QUEST_MARKER_THRESHOLD:
                    if last_marker_pos is not None:
                        dist = np.hypot(tx - last_marker_pos[0], ty - last_marker_pos[1])
                        if dist < 15:
                            marker_stuck_count += 1
                        else:
                            marker_stuck_count = 0
                    last_marker_pos = (tx, ty)
                else:
                    marker_stuck_count = 0
                    last_marker_pos = None

                if now - follow_rule.last > FOLLOW_COOLDOWN:
                    if marker_stuck_count > 20:
                        print(f"[PATH] Target is stuck. Walking to ({tx}, {ty})...", flush=True)
                        walk_to_quest_marker(gray, bgr, cw, ch)
                        follow_rule.last = time.time() - FOLLOW_COOLDOWN + 1.0
                        marker_stuck_count = 0
                    else:
                        if pressed_once:
                            if motion["moved"]:
                                still_count = 0
                                nudge_streak = 0
                            else:
                                still_count += 1
                            print(f"[stuck?] since last press: {'MOVED' if motion['moved'] else 'DID NOT MOVE'} "
                                  f"(max scene scroll {motion['max']:.2f}px, threshold {MOVE_PX}) | consecutive still: {still_count}/{STUCK_PRESSES}", flush=True)
                        if still_count >= STUCK_PRESSES:
                            if nudge_streak >= MAX_NUDGES:
                                trigger_pause(f"Character is stuck on the map: nudged the joystick {nudge_streak} times in a row and still cannot move "
                                              f"(possible obstacle / puzzle / something that needs manual action)", bgr)
                                nudge_streak = 0
                                still_count = 0
                                continue
                            if debug_mode: save_debug(bgr, "Stuck - joystick nudge", None, None, None)
                            nudge_joystick(client_x, client_y, cw, ch, nudge_idx)
                            nudge_idx += 1
                            nudge_streak += 1
                            still_count = 0
                            time.sleep(0.4)
                            gray, bgr = grab(client_x, client_y, cw, ch)
                        reset_motion(motion)
                        pressed_once = True
                        matched = False
                        for f in follow_rule.files:
                            s, cx, cy, rect = match(gray, f, follow_rule.threshold, follow_rule.roi)
                            if cx is not None:
                                print(f"[CLICK] Follow ({f}) matched {s:.2f}", flush=True)
                                if debug_mode: save_debug(bgr, "Follow", cx, cy, rect)
                                click_fast(client_x + cx, client_y + cy)
                                matched = True
                                break
                        if not matched:
                            print("[CLICK] Follow (fixed coordinates)", flush=True)
                            click_fast(client_x + int(cw * FOLLOW_REL[0]), client_y + int(ch * FOLLOW_REL[1]))
                        follow_rule.last = time.time()
                        last_action = time.time()
            else:
                reset_motion(motion)
                pressed_once = False
                still_count = 0
                nudge_streak = 0
                t_now = time.time()
                if unknown_since is None:
                    unknown_since = t_now
                if t_now < battle_grace_until:
                    unknown_since = t_now
                elif t_now - unknown_since > UNKNOWN_TIMEOUT:
                    _sc, bx, _by, _r = match(gray, "in_battle.png", 0.90, None)
                    if bx is not None:
                        unknown_since = t_now
                    else:
                        trigger_pause(f"Unknown screen: nothing matched for {UNKNOWN_TIMEOUT:.0f} seconds (possibly a puzzle)", bgr)
                        continue
                if time.time() - last_action > TAP_IDLE:
                    stuck_frames += 1
                    if stuck_frames >= 3:
                        print(f"[RESCUE] Stuck {stuck_frames} times. Trying to find the blue diamond to walk to...", flush=True)
                        if not walk_to_quest_marker(gray, bgr, cw, ch):
                            print("[RESCUE] No diamond found. Pressing Follow...", flush=True)
                            click_fast(client_x + int(cw * FOLLOW_REL[0]), client_y + int(ch * FOLLOW_REL[1]))
                        stuck_frames = 0
                    else:
                        print(f"[ANTI-STUCK] Attempt {stuck_frames}/3. Clicking the 'Tap to continue' area", flush=True)
                        click_fast(client_x + int(cw * TAP_CONTINUE_REL[0]), client_y + int(ch * TAP_CONTINUE_REL[1]))
                    last_action = time.time()
                    time.sleep(1.0)
                else:
                    stuck_frames = 0

            time.sleep(LOOP_DELAY)

    except KeyboardInterrupt:
        print("\n[INFO] Stopped with Ctrl+C.", flush=True)

if __name__ == "__main__":
    if not os.path.isdir(TEMPLATE_DIR):
        print(f"[ERROR] Folder not found: {TEMPLATE_DIR}")
        print("Create a 'templates' folder next to afk_bot.py and put the button images (.png) in it. See README.md.")
        sys.exit(1)
    main()
