// ==UserScript==
// @name         Victordle Auto Guesser
// @namespace    http://tampermonkey.net/
// @version      1.4.1
// @description  Automates Victordle (Duel) instantly using a MutationObserver and a Python solver backend.
// @author       KHROTU
// @match        https://www.britannica.com/games/victordle/mode-2
// @icon         https://www.google.com/s2/favicons?sz=64&domain=https://www.britannica.com/games/victordle/mode-2
// @grant        GM_xmlhttpRequest
// @connect      localhost
// ==/UserScript==

(function() {
    'use strict';

    const PYTHON_SERVER_URL = 'http://localhost:8765';
    const FIRST_GUESS = 'ARISE';

    class VictordleGuesser {
        constructor() {
            this.isActive = false;
            this.isThinking = false;
            this.lastGuessCount = -1;
            this.setupUI();
            this.waitForBoardAndInitialize();
        }

        log(message) {
            console.log(`[Victordle Guesser] ${message}`);
        }

        setupUI() {
            const panel = document.createElement('div');
            panel.id = 'guesser-panel';
            panel.style.cssText = `
                position: fixed; top: 10px; right: 10px; width: 250px; background: #333;
                color: #eee; padding: 10px; z-index: 10001; font-family: sans-serif;
                font-size: 14px; border: 1px solid #555;
            `;

            panel.innerHTML = `
                <h3 style="margin: 0 0 10px 0; color: #eee; text-align: center; font-weight: normal;">Victordle Solver</h3>
                <div id="guesser-status" style="margin-bottom: 10px; min-height: 18px; text-align: center; color: #ccc;">Ready</div>
                <button id="toggle-guesser" style="width: 100%; padding: 10px; font-size: 16px; cursor: pointer; border: 1px solid #444; background-color: #008040; color: white;">
                    START
                </button>
                <details id="guesser-debug-details" style="margin-top: 10px; font-size: 12px; color: #bdc3c7; border-top: 1px solid #555; padding-top: 10px;">
                    <summary style="cursor: pointer; color: #ccc;">Debug Info</summary>
                    <pre id="guesser-debug-info" style="background: #222; padding: 8px; margin-top: 5px; white-space: pre-wrap; word-break: break-all; color: #aaffaa; font-family: monospace; font-size: 11px;"></pre>
                </details>
            `;
            document.body.appendChild(panel);

            this.statusEl = document.getElementById('guesser-status');
            this.toggleBtn = document.getElementById('toggle-guesser');
            this.debugInfoEl = document.getElementById('guesser-debug-info');

            this.toggleBtn.addEventListener('click', () => this.toggleActive());
            this.updateDebugInfo({ status: "Panel initialized." });
        }

        waitForBoardAndInitialize() {
            const boardFinder = setInterval(() => {
                const board = document.querySelector('.board-item');
                if (board) {
                    clearInterval(boardFinder);
                    const observer = new MutationObserver(() => {
                        if (this.isActive) {
                            this.mainLoop();
                        }
                    });
                    observer.observe(board, { attributes: true, subtree: true, attributeFilter: ['class'] });
                    this.log("MutationObserver attached to game board.");
                }
            }, 500);
        }

        updateStatus(text, color = '#ccc') {
            if (this.statusEl) {
                this.statusEl.textContent = text;
                this.statusEl.style.color = color;
            }
        }

        updateDebugInfo(data) {
            if (this.debugInfoEl) {
                this.debugInfoEl.textContent = JSON.stringify(data, null, 2);
            }
        }

        toggleActive() {
            this.isActive = !this.isActive;
            if (this.isActive) {
                this.log("Automation started.");
                this.toggleBtn.textContent = 'PAUSE';
                this.toggleBtn.style.backgroundColor = '#c00';
                this.lastGuessCount = -1;
                this.mainLoop();
            } else {
                this.log("Automation paused.");
                this.toggleBtn.textContent = 'START';
                this.toggleBtn.style.backgroundColor = '#008040';
                this.updateStatus("Paused by user");
            }
        }

        async mainLoop() {
            if (this.isThinking) return;

            try {
                this.isThinking = true;
                const boardState = this.scrapeBoardState();
                if (!boardState) {
                    this.updateStatus("Can't find board", '#ff5555');
                    return;
                }

                if (boardState.isSolved) {
                    this.updateStatus("Solved!", '#55ff55');
                    this.toggleActive();
                    return;
                }

                if (boardState.guesses.length === this.lastGuessCount) return;

                this.log(`Board state changed. Found ${boardState.guesses.length} completed guesses.`);
                this.lastGuessCount = boardState.guesses.length;
                this.updateDebugInfo({ lastPayload: boardState.guesses });

                if (boardState.guesses.length === 0 && this.isActive) {
                    this.updateStatus(`Typing first guess: ${FIRST_GUESS}`);
                    await this.typeWord(FIRST_GUESS);
                    return;
                }

                if (boardState.guesses.length > 0) {
                    this.updateStatus("Querying solver...");
                    const response = await this.sendToPython(boardState.guesses);

                    if (response && response.next_guess) {
                        this.log(`Solver suggested: ${response.next_guess}`);
                        this.updateDebugInfo({ solverResponse: response });
                        this.updateStatus(`Typing: ${response.next_guess}`);
                        await this.typeWord(response.next_guess);
                    } else {
                        this.updateStatus("No suggestion from solver", '#ffaa55');
                        this.updateDebugInfo({ solverResponse: response });
                    }
                }
            } catch (error) {
                this.log(`Error in main loop: ${error.message}`);
                this.updateStatus("Solver connection failed!", '#ff5555');
                this.updateDebugInfo({ error: error.message });
                this.toggleActive();
            } finally {
                this.isThinking = false;
            }
        }

        scrapeBoardState() {
            const board = document.querySelector('.board-item');
            if (!board) return null;

            const guesses = [];
            let isSolved = false;
            const rows = board.querySelectorAll('.Row');

            for (const row of rows) {
                const tiles = Array.from(row.children);
                if (tiles.length !== 5) continue;

                const word = tiles.map(tile => tile.textContent.trim().toUpperCase()).join('');
                if (word.length !== 5) continue;

                let feedback = '';
                for (const tile of tiles) {
                    const classList = tile.classList;
                    if (classList.contains('letter-correct')) feedback += 'G';
                    else if (classList.contains('letter-elsewhere')) feedback += 'Y';
                    else if (classList.contains('letter-absent')) feedback += 'X';
                    else { feedback = ''; break; }
                }

                if (feedback.length === 5) {
                    guesses.push({ word, feedback });
                    if (feedback === 'GGGGG') isSolved = true;
                }
            }
            return { guesses, isSolved };
        }

        sendToPython(guesses) {
            return new Promise((resolve, reject) => {
                GM_xmlhttpRequest({
                    method: 'POST',
                    url: PYTHON_SERVER_URL,
                    headers: { 'Content-Type': 'application/json' },
                    data: JSON.stringify({ action: 'process_guesses', guesses }),
                    onload: (response) => {
                        if (response.status >= 200 && response.status < 300) {
                            resolve(JSON.parse(response.responseText));
                        } else {
                            reject(new Error(`HTTP Error: ${response.status}`));
                        }
                    },
                    onerror: () => reject(new Error('Network error or server down.')),
                });
            });
        }

        async typeWord(word) {
            this.log(`Typing: ${word}`);
            for (const char of word) {
                this.simulateKeyPress(char.toLowerCase());
                await new Promise(resolve => setTimeout(resolve, 10));
            }
            await new Promise(resolve => setTimeout(resolve, 25));
            this.simulateKeyPress('Enter');
            this.updateStatus("Waiting for feedback...");
        }

        simulateKeyPress(key) {
            const eventProps = {
                key: key,
                code: key === 'Enter' ? 'Enter' : `Key${key.toUpperCase()}`,
                bubbles: true,
                cancelable: true,
            };
            document.body.dispatchEvent(new KeyboardEvent('keydown', eventProps));
        }
    }

    window.addEventListener('load', () => {
        setTimeout(() => { new VictordleGuesser(); }, 2000);
    });
})();