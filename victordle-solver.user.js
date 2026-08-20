// ==UserScript==
// @name         Victordle Auto Guesser
// @namespace    http://tampermonkey.net/
// @version      1.5.1
// @description  Automates Victordle (Duel) using Entropy-based solving and supports a continuous Manual Mode.
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
                position: fixed;
                top: 10px;
                right: 10px;
                width: 260px;
                background: rgba(30, 30, 30, 0.95);
                color: #eee;
                padding: 15px;
                z-index: 2147483647;
                font-family: 'Segoe UI', Roboto, Helvetica, Arial, sans-serif;
                font-size: 14px;
                border: 1px solid #555;
                border-radius: 8px;
                box-shadow: 0 4px 12px rgba(0,0,0,0.5);
            `;

            panel.innerHTML = `
                <h3 style="margin: 0 0 15px 0; color: #fff; text-align: center; font-weight: 600; font-size: 16px; border-bottom: 1px solid #555; padding-bottom: 10px;">Victordle Solver</h3>
                
                <div id="guesser-status" style="margin-bottom: 15px; min-height: 20px; text-align: center; color: #ccc; font-weight: 500;">Ready</div>
                
                <div style="margin-bottom: 15px; display: flex; align-items: center; justify-content: center; background: #444; padding: 8px; border-radius: 4px;">
                    <input type="checkbox" id="manual-mode-chk" style="margin-right: 8px; cursor: pointer; transform: scale(1.2);">
                    <label for="manual-mode-chk" style="cursor: pointer; font-size: 13px; color: #fff; user-select: none;">Manual Mode (Hints Only)</label>
                </div>

                <button id="toggle-guesser" style="width: 100%; padding: 12px; font-size: 14px; font-weight: bold; cursor: pointer; border: none; border-radius: 4px; background-color: #2ecc71; color: white; transition: background 0.2s;">
                    START AUTO-BOT
                </button>

                <div id="solver-suggestions" style="margin-top: 15px; display: none; background: #2c3e50; padding: 10px; border-radius: 4px; border-left: 4px solid #3498db;">
                   <div style="font-size: 11px; text-transform: uppercase; color: #bdc3c7; margin-bottom: 5px; font-weight: bold;">Recommended:</div>
                   <div id="suggestion-list" style="font-family: 'Consolas', 'Monaco', monospace; color: #ecf0f1; font-size: 14px; line-height: 1.4;"></div>
                </div>

                <details id="guesser-debug-details" style="margin-top: 15px; font-size: 12px; color: #7f8c8d; border-top: 1px solid #444; padding-top: 10px;">
                    <summary style="cursor: pointer; color: #95a5a6;">Debug Info</summary>
                    <pre id="guesser-debug-info" style="background: #222; padding: 8px; margin-top: 5px; white-space: pre-wrap; word-break: break-all; color: #27ae60; font-family: monospace; font-size: 10px; border-radius: 4px;"></pre>
                </details>
            `;
            document.body.appendChild(panel);

            this.statusEl = document.getElementById('guesser-status');
            this.toggleBtn = document.getElementById('toggle-guesser');
            this.debugInfoEl = document.getElementById('guesser-debug-info');
            this.manualModeChk = document.getElementById('manual-mode-chk');
            this.suggestionsBox = document.getElementById('solver-suggestions');
            this.suggestionList = document.getElementById('suggestion-list');

            this.toggleBtn.addEventListener('click', () => this.toggleActive());
            
            this.manualModeChk.addEventListener('change', () => {
                const isManual = this.manualModeChk.checked;
                this.log(`Manual mode toggled: ${isManual}`);
                
                if (isManual) {
                    this.toggleBtn.style.display = 'none';
                    this.updateStatus("Manual Mode Active");
                    this.suggestionsBox.style.display = 'block';
                    this.mainLoop();
                } else {
                    this.toggleBtn.style.display = 'block';
                    this.suggestionsBox.style.display = 'none';
                    this.updateStatus("Ready");
                    this.lastGuessCount = -1;
                }
            });

            this.updateDebugInfo({ status: "Panel initialized." });
        }

        waitForBoardAndInitialize() {
            const boardFinder = setInterval(() => {
                const board = document.querySelector('.board-item');
                if (board) {
                    clearInterval(boardFinder);
                    const observer = new MutationObserver(() => {
                        if (this.isActive || (this.manualModeChk && this.manualModeChk.checked)) {
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

        showSuggestions(response) {
            this.suggestionsBox.style.display = 'block';
            
            let content = '';
            if (response.next_guess) {
                content += `<span style="color: #3498db; font-weight: bold;">${response.next_guess}</span>`;
            }
            
            if (response.options && response.options.length > 0) {
                 const others = response.options.filter(w => w !== response.next_guess).slice(0, 4);
                 if (others.length > 0) {
                     content += `<div style="margin-top:5px; color: #7f8c8d; font-size: 12px;">Alts: ${others.join(', ')}</div>`;
                 }
            }
            
            if (!content) content = "No clear suggestion.";
            this.suggestionList.innerHTML = content;
        }

        toggleActive() {
            this.isActive = !this.isActive;
            if (this.isActive) {
                this.log("Automation started.");
                this.toggleBtn.textContent = 'PAUSE AUTO-BOT';
                this.toggleBtn.style.backgroundColor = '#e74c3c';
                this.lastGuessCount = -1;
                this.mainLoop();
            } else {
                this.log("Automation paused.");
                this.toggleBtn.textContent = 'START AUTO-BOT';
                this.toggleBtn.style.backgroundColor = '#2ecc71';
                this.updateStatus("Paused by user");
            }
        }

        async mainLoop() {
            if (this.isThinking) return;

            try {
                this.isThinking = true;
                const boardState = this.scrapeBoardState();
                if (!boardState) {
                    this.updateStatus("Can't find board", '#e74c3c');
                    return;
                }

                if (boardState.isSolved) {
                    this.updateStatus("Solved!", '#2ecc71');
                    if (this.isActive) this.toggleActive();
                    return;
                }

                if (this.isActive && boardState.guesses.length === this.lastGuessCount) return;

                this.log(`Board state analysis. Guesses found: ${boardState.guesses.length}`);
                this.lastGuessCount = boardState.guesses.length;
                this.updateDebugInfo({ lastPayload: boardState.guesses });

                const isManual = this.manualModeChk.checked;

                if (boardState.guesses.length === 0) {
                    if (isManual) {
                        this.updateStatus("Waiting for first guess...");
                        this.showSuggestions({ next_guess: FIRST_GUESS, options: [] });
                    } else if (this.isActive) {
                        this.updateStatus(`Typing first guess: ${FIRST_GUESS}`);
                        await this.typeWord(FIRST_GUESS);
                    }
                    return;
                }

                if (boardState.guesses.length > 0) {
                    this.updateStatus("Thinking...");
                    const response = await this.sendToPython(boardState.guesses);

                    if (response && response.next_guess) {
                        this.log(`Solver suggested: ${response.next_guess}`);
                        this.updateDebugInfo({ solverResponse: response });
                        
                        if (isManual) {
                            this.updateStatus("Suggestion Ready", '#3498db');
                            this.showSuggestions(response);
                        } else if (this.isActive) {
                            this.updateStatus(`Typing: ${response.next_guess}`);
                            await this.typeWord(response.next_guess);
                        }
                    } else {
                        this.updateStatus("No suggestion found", '#f39c12');
                        this.updateDebugInfo({ solverResponse: response });
                    }
                }
            } catch (error) {
                this.log(`Error in main loop: ${error.message}`);
                this.updateStatus("Connection Error", '#e74c3c');
                this.updateDebugInfo({ error: error.message });
                if (this.isActive) this.toggleActive();
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