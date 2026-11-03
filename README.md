
# AFK Journey Map Runner Bot

A Windows automation tool that plays through the story/map progression of the PC version of **AFK Journey** by itself. It watches the game window, recognizes buttons and screens with OpenCV template matching, and clicks the right thing at the right time: following the quest, skipping dialogue, confirming popups, starting fights, closing result screens and holding the "press and hold" prompts.

When it meets something it cannot handle (for example a puzzle), it stops clicking, beeps, and waits for you.

> **Disclaimer:** this project is not affiliated with or endorsed by the game's publisher. Automating a game may violate its Terms of Service and could put your account at risk. Use it at your own risk.

## What it does

| Situation | What the bot does |
|---|---|
| Quest "Follow" button on the map | Presses it again every few seconds so the character keeps walking to the objective |
| Character stands still after pressing Follow | Detects that the scene is not scrolling, nudges the joystick a little in a different direction each time, then presses Follow again |
| Dialogue / cutscene | Presses **Skip**, including on fully dark cutscene screens |
| Dialogue choices | Picks the first option |
| Confirmation popups | Clicks the green check |
| **Battle** button | Presses it and confirms; stays quiet for 90 seconds while the fight runs |
| Victory / quest-complete screens | Clicks the "tap to close / continue" prompt |
| "Press and hold" circle | Detects the orange circle with the F key below it and holds it for a few seconds |
| Interact prompt (F key) | Presses `F` (needs the optional `gift_f_button.png` template) |
| Unknown screen, or stuck on the map | Stops clicking, beeps every few seconds, saves a screenshot, and waits until you press `F9` |

## Requirements

- Windows (the tool uses `win32gui`, `winsound` and DPI-awareness calls)
- Python 3 (developed on Python 3.13) and `pip`
- AFK Journey for PC running in **windowed mode**, with the window title `AFK Journey`
- Recommended client area: **1280x768** (the template images were captured at this size)
- The game UI language must match your template images. The templates used by the author were cropped from the Vietnamese client; for another language you need to capture your own (see [Templates](#templates))

## Installation

```
git clone https://github.com/hcefptu/AFK_Journey_Automate_Map
cd <repository-folder>
pip install -r requirements.txt
```

## Running the bot

The bot needs administrator rights so the `keyboard` library can read the `F8` / `F9` hotkeys.

1. Open the Start menu, type `cmd`, right-click **Command Prompt** and choose **Run as administrator**.
2. Go to the folder that contains `afk_bot.py` then righ click and **Copy as path**. Use `cd /d + paste the path`
The path might be:

   ```
   cd /d "C:\path\to\the\folder\with\afk_bot.py"
   ```

3. Start the game, put it in windowed mode, and open the map you want to run.
4. Run the bot:

   ```
   python afk_bot.py
   ```

The console prints `Connected to the game window` when it finds the game. All files the bot reads and writes (`templates/`, `debug/`, `shots/`) are located relative to `afk_bot.py`, so it works the same wherever you put the folder, even if the path contains spaces or non-English characters.

### Command-line options

| Command | Purpose |
|---|---|
| `python afk_bot.py` | Run the bot |
| `python afk_bot.py --debug` | Run the bot and save an annotated screenshot (green box on the match, red dot on the click) to `debug/<date>/` for most clicks |
| `python afk_bot.py --shot` | Wait 3 seconds, capture the game window to `shots/`, and exit. Use this to make template images |

### Hotkeys

| Key | Action |
|---|---|
| `F8` | Quit the bot |
| `F9` | Pause / resume. After an automatic stop ("waiting for you"), solve the situation in the game and press `F9` to continue |

Emergency stop: move the mouse to the top-left corner of the screen. PyAutoGUI's fail-safe then aborts the bot with an error message.

## Templates

The bot finds buttons by comparing the screen with small PNG images in the `templates/` folder, which must sit next to `afk_bot.py`. Missing images are reported at startup as `[WARNING] Missing template images ...`.

**How to make them:** run `python afk_bot.py --shot` while the button is on screen, open the image in `shots/`, and crop just the button into `templates/` with the exact file name below. The bot searches many sizes (0.05x to about 2.5x) and remembers the best one in `templates/scales.json`, so the crop does not need to be pixel-perfect in size.

| File | What it is |
|---|---|
| `tick_xanh.png` | Green check button on confirmation popups |
| `bo_qua_1.png`, `bo_qua_2.png` | The round **Skip** button (two variants with different backgrounds) |
| `chien_dau.png` | The green **Battle** button |
| `hoi_thoai_1.png`, `icon_hoi_thoai.png` | The quest "?" icon in the first dialogue option |
| `nhan_de_dong.png`, `nhan_de_tiep_tuc.png` | The "tap to close" / "tap to continue" prompts |
| `theo_doi_1.png`, `theo_doi_2.png`, `theo_doi_3.png` | The **Follow** button with a diamond, "?" and "!" icon. The bot crops them to the inner circle automatically |

Optional images:

| File | What it is |
|---|---|
| `hud_joystick.png` | The centre of the on-screen joystick. Helps the bot recognize that it is on the map |
| `in_battle.png` | The pause icon shown during a fight, so long fights are not treated as an unknown screen |
| `gift_f_button.png` | The interact prompt that is triggered with the `F` key |
| `quest_marker.png` | The quest marker icon. If the marker stays frozen, the bot walks toward it with `W`/`A`/`S`/`D` |

`templates/scales.json` is generated by the bot for your own screen and should not be shared between machines.

## Configuration

Everything is configured with constants at the top of `afk_bot.py`.

| Constant | Default | Meaning |
|---|---|---|
| `GAME_WINDOW_TITLE` | `"AFK Journey"` | Text the game window title must contain |
| `FOLLOW_COOLDOWN` | `2.5` | Seconds between presses of the Follow button |
| `MOVE_PX` | `1.5` | Scene scroll (in pixels) that counts as "the character is moving" |
| `NUDGE_MODE` | `"mouse"` | How to nudge: `"mouse"` drags the joystick, `"keys"` presses `W`/`A`/`S`/`D` |
| `JOY_REL`, `JOY_DRAG_PX`, `NUDGE_HOLD` | `(0.50, 0.776)`, `30`, `0.6` | Joystick position (fraction of the window), drag distance and hold time |
| `MAX_NUDGES` | `4` | Nudges in a row without progress before the bot stops and calls you |
| `UNKNOWN_TIMEOUT` | `15.0` | Seconds on an unrecognized screen before the bot stops and calls you |
| `BATTLE_GRACE` | `90.0` | Seconds after pressing Battle during which an unknown screen is treated as a fight |
| `ALARM_EVERY` | `8.0` | Seconds between beeps while waiting for you |
| `HOLD_DURATION` | `5.5` | Seconds to hold the "press and hold" circle |

## When the bot stops and beeps

It prints `[WAITING FOR YOU]` with the reason, stops all clicking, beeps every few seconds and saves a screenshot to `debug/unknown/<date>/`. Solve the puzzle or situation yourself in the game, then press `F9`. Those screenshots are also handy for adding new templates or reporting issues.

## Troubleshooting

- **No "Connected to the game window" line:** the game window was not found. Make sure the game is running in windowed mode (not minimized) and that `GAME_WINDOW_TITLE` matches its title bar.
- **`F8` / `F9` do nothing:** the command prompt was not started as administrator.
- **`[WARNING] Missing template images`:** add the listed files to `templates/`.
- **Buttons are seen but clicks land in the wrong place:** keep the whole game window on screen. The bot enables DPI awareness itself, so Windows display scaling (125%, 150%) should not matter.
- **A button is never clicked:** run with `--debug`, look at the `[CLICK]` lines and screenshots, and re-crop that template from a fresh `--shot`. A different game language or client version needs its own templates.
- **The bot keeps stopping on long fights:** add `in_battle.png`, or raise `BATTLE_GRACE` / `UNKNOWN_TIMEOUT`.

## Project layout

```
afk_bot.py          the bot
requirements.txt    Python dependencies
templates/          button images (you provide; scales.json is generated)
debug/              screenshots saved by --debug and by automatic stops (generated)
shots/              screenshots saved by --shot (generated)
```