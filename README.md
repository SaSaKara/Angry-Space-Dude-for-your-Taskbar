# Desktop Pet

A small animated desktop pet built with Python and Tkinter.

## Features

- Transparent window
- Gravity-based spawn from the top of the screen
- Walk / idle / fire / drag / descend states
- Random direction changes
- Right-click context menu
- Pause / resume with Space
- Exit with Escape
- Asset fallback support

## Project Structure

```text
desktop-pet/
│
├─ main.py
├─ README.md
├─ requirements.txt
├─ .gitignore
│
├─ pet/
│   ├─ __init__.py
│   ├─ app.py
│   └─ utils.py
│
└─ assets/