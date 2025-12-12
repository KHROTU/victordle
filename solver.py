import argparse
import collections
import concurrent.futures
import json
import os
import pickle
import sys
import time
from functools import partial
from http.server import BaseHTTPRequestHandler, HTTPServer
from typing import Dict, List, Tuple

WORD_LENGTH = 5
WORD_LIST_FILENAME = "words.txt"
MATRIX_FILENAME = "feedback_matrix.pkl"
SERVER_PORT = 8765

class VicSolver:
    def __init__(self, all_words: List[str], feedback_matrix: Dict[Tuple[str, str], str]):
        self.all_words = all_words
        self.feedback_matrix = feedback_matrix
        self.possible_words = list(self.all_words)
        self.guess_count = 0

    def _calculate_guess_score(self, guess: str) -> int:
        if not self.possible_words:
            return 0

        feedback_groups = collections.defaultdict(int)
        for target_word in self.possible_words:
            feedback = self.feedback_matrix.get((guess, target_word), "")
            feedback_groups[feedback] += 1

        return max(feedback_groups.values()) if feedback_groups else 0

    def get_best_guess(self) -> str:
        if not self.possible_words:
            return ""

        if len(self.possible_words) <= 2:
            return self.possible_words[0]

        best_candidate = (float('inf'), True, "")

        for guess in self.all_words:
            score = self._calculate_guess_score(guess)
            is_possible = guess in self.possible_words
            candidate = (score, not is_possible, guess)

            if candidate < best_candidate:
                best_candidate = candidate
                if best_candidate[0] == 1 and not best_candidate[1]:
                    return best_candidate[2]

        return best_candidate[2]

    def apply_feedback(self, guess: str, feedback: str):
        if len(guess) != WORD_LENGTH or len(feedback) != WORD_LENGTH:
            return

        self.possible_words = [
            word for word in self.possible_words
            if self.feedback_matrix.get((guess, word)) == feedback
        ]
        self.guess_count += 1

    def get_status(self) -> dict:
        if len(self.possible_words) == 1:
            next_guess = self.possible_words[0]
        else:
            next_guess = self.get_best_guess()

        return {
            "possible_words_count": len(self.possible_words),
            "next_guess": next_guess,
            "options": self.possible_words[:10] if len(self.possible_words) <= 10 else []
        }

def get_feedback(guess: str, target: str) -> str:
    feedback = ['X'] * WORD_LENGTH
    target_counts = collections.Counter(target)
    
    for i in range(WORD_LENGTH):
        if guess[i] == target[i]:
            feedback[i] = 'G'
            target_counts[guess[i]] -= 1

    for i in range(WORD_LENGTH):
        if feedback[i] == 'G':
            continue
        if guess[i] in target_counts and target_counts[guess[i]] > 0:
            feedback[i] = 'Y'
            target_counts[guess[i]] -= 1
    
    return "".join(feedback)

def compute_row_for_guess(guess: str, all_words: Tuple[str, ...]) -> Dict[Tuple[str, str], str]:
    return {(guess, target): get_feedback(guess, target) for target in all_words}

def load_words(filename: str) -> List[str]:
    if not os.path.exists(filename):
        print(f"Error: Word list file '{filename}' not found.", file=sys.stderr)
        print("Please create it and populate it with 5-letter words, one per line.", file=sys.stderr)
        sys.exit(1)
    
    try:
        with open(filename, 'r') as f:
            words = {
                line.strip().upper() for line in f
                if len(line.strip()) == WORD_LENGTH and line.strip().isalpha()
            }
    except Exception as e:
        print(f"Error reading word list file '{filename}': {e}", file=sys.stderr)
        sys.exit(1)

    if not words:
        print(f"Error: No valid {WORD_LENGTH}-letter words found in '{filename}'.", file=sys.stderr)
        sys.exit(1)

    return sorted(list(words))

def precompute_and_save():
    print("Starting pre-computation of the feedback matrix.")
    if os.path.exists(MATRIX_FILENAME):
        print(f"'{MATRIX_FILENAME}' already exists. Skipping.")
        return

    all_words = load_words(WORD_LIST_FILENAME)
    num_words = len(all_words)
    total_calculations = num_words * num_words
    max_workers = os.cpu_count() or 4

    print(f"Loaded {num_words} words from '{WORD_LIST_FILENAME}'.")
    print(f"Preparing to compute {total_calculations:,} feedback results using up to {max_workers} processes.")
    print("This may take several minutes...")

    start_time = time.time()
    feedback_matrix = {}

    with concurrent.futures.ProcessPoolExecutor(max_workers=max_workers) as executor:
        worker_func = partial(compute_row_for_guess, all_words=tuple(all_words))
        chunksize = max(1, num_words // (max_workers * 4))
        results_iterator = executor.map(worker_func, all_words, chunksize=chunksize)
        
        for i, row_dict in enumerate(results_iterator):
            feedback_matrix.update(row_dict)
            progress = (i + 1) / num_words
            elapsed_time = time.time() - start_time
            sys.stdout.write(
                f"\r  Progress: [{int(progress * 30) * '='}>{(30 - int(progress * 30)) * ' '}] "
                f"{i + 1}/{num_words} ({progress:.1%}) | Elapsed: {elapsed_time:.1f}s"
            )
            sys.stdout.flush()

    total_time = time.time() - start_time
    print(f"\n\nComputation complete in {total_time:.2f} seconds.")

    print(f"Saving matrix to '{MATRIX_FILENAME}'...")
    try:
        with open(MATRIX_FILENAME, 'wb') as f:
            pickle.dump(feedback_matrix, f, protocol=pickle.HIGHEST_PROTOCOL)
        file_size = os.path.getsize(MATRIX_FILENAME) / (1024 * 1024)
        print(f"Successfully saved. File size: {file_size:.2f} MB")
    except Exception as e:
        print(f"Error saving file: {e}", file=sys.stderr)
        sys.exit(1)

ALL_WORDS = []
FEEDBACK_MATRIX = {}

def load_data_for_server():
    global ALL_WORDS, FEEDBACK_MATRIX
    print("Loading data for server...")
    ALL_WORDS = load_words(WORD_LIST_FILENAME)
    
    try:
        with open(MATRIX_FILENAME, 'rb') as f:
            FEEDBACK_MATRIX = pickle.load(f)
    except FileNotFoundError:
        print(f"FATAL: Could not find matrix '{MATRIX_FILENAME}'.", file=sys.stderr)
        print("Please run 'python solver.py --precompute' first.", file=sys.stderr)
        sys.exit(1)
    except Exception as e:
        print(f"FATAL: Could not load matrix '{MATRIX_FILENAME}'. Error: {e}", file=sys.stderr)
        sys.exit(1)
    
    print(f"Data loaded: {len(ALL_WORDS)} words and {len(FEEDBACK_MATRIX)} matrix entries.")

class SolverHTTPHandler(BaseHTTPRequestHandler):
    def do_POST(self):
        try:
            content_length = int(self.headers['Content-Length'])
            post_data = self.rfile.read(content_length)
            data = json.loads(post_data.decode('utf-8'))
        except (TypeError, json.JSONDecodeError):
            self.send_error(400, "Invalid JSON")
            return

        action = data.get('action')
        response = {}

        if action == 'process_guesses':
            guesses = data.get('guesses', [])
            print(f"\n[Request] Received board state: {guesses}")

            solver = VicSolver(ALL_WORDS, FEEDBACK_MATRIX)
            for guess_data in guesses:
                word = guess_data.get('word', '').upper()
                feedback = guess_data.get('feedback', '')
                solver.apply_feedback(word, feedback)

            print(f"[Solver] {len(solver.possible_words)} possible words remain.")
            status = solver.get_status()
            print(f"[Solver] Best guess: '{status['next_guess']}'")
            
            response = {
                "next_guess": status['next_guess'],
                "possible_words_count": status['possible_words_count']
            }
        else:
            response = {"error": "Invalid action"}

        self.send_response(200)
        self.send_header('Content-type', 'application/json')
        self.send_header('Access-Control-Allow-Origin', '*')
        self.end_headers()
        self.wfile.write(json.dumps(response).encode('utf-8'))

    def do_OPTIONS(self):
        self.send_response(204)
        self.send_header('Access-Control-Allow-Origin', '*')
        self.send_header('Access-Control-Allow-Methods', 'POST, OPTIONS')
        self.send_header('Access-Control-Allow-Headers', 'Content-Type')
        self.end_headers()

    def log_message(self, format, *args):
        return

def start_server():
    try:
        server = HTTPServer(('localhost', SERVER_PORT), SolverHTTPHandler)
        print(f"Server started on http://localhost:{SERVER_PORT}")
        print("Ready for Victordle userscript. Press Ctrl+C to exit.")
        server.serve_forever()
    except OSError as e:
        print(f"Error: Port {SERVER_PORT} is already in use.", file=sys.stderr)
        print(e, file=sys.stderr)
    except KeyboardInterrupt:
        print("\nShutting down server.")
    finally:
        print("Server stopped.")

def main():
    parser = argparse.ArgumentParser(
        description="A high-performance backend for the Victordle Solver userscript.",
        formatter_class=argparse.RawTextHelpFormatter
    )
    parser.add_argument(
        '--precompute',
        action='store_true',
        help="Run the one-time pre-computation of the feedback matrix.\nThis will create a 'feedback_matrix.pkl' file from 'words.txt'."
    )
    args = parser.parse_args()

    if args.precompute:
        precompute_and_save()
    else:
        print("--- Victordle Automation Server ---")
        load_data_for_server()
        start_server()

if __name__ == "__main__":
    main()