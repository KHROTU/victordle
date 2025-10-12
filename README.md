# Victordle Solver

A high-performance, automated solver for the web game Victordle (Duel).

---

## Features

- **Instantaneous:** Solves puzzles almost instantly using a pre-computed backend.
- **Optimal:** Uses a min-max algorithm to determine the best possible guess at each step.
- **Automated:** Automatically types guesses into the game via a userscript.

---

## Requirements

- Python 3.8+
- A web browser with the [Tampermonkey](https://www.tampermonkey.net/) (or equivalent) extension.

---

## Setup

**1. Pre-compute the Solver Matrix (One-time step)**

This step creates a `feedback_matrix.pkl` file which is essential for the solver's speed. It may take several minutes to complete depending on your CPU.

```shell
cd wordle
python precompute.py
```

**2. Run the Backend Server**

This server must be running in the background while you are playing the game.

```shell
python victordle_automation.py
```

**3. Install the Userscript**

- Open the Tampermonkey extension dashboard in your browser.
- Create a new script (`+` icon).
- Copy the content of `victordle-solver.user.js` and paste it into the editor, replacing the default template.
- Save the script (File -> Save or `Ctrl+S`).

---

## Usage

1. Ensure the Python server from **Setup Step 2** is running.
2. Navigate to [Victordle (Duel)](https://www.britannica.com/games/victordle/mode-2).
3. The solver panel will appear in the top-right corner of the page.
4. Click **START** to begin the automated solving process.
