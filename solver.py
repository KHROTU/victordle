import argparse
import collections
import json
import math
import os
import pickle
import sys
import time
import concurrent.futures
from functools import lru_cache, partial
from http.server import BaseHTTPRequestHandler, HTTPServer
from typing import Dict, List, Tuple

WORD_LENGTH = 5
PRECOMPUTED_FIRST_GUESS = "RAISE"
WORD_LIST_FILENAME = "words.txt"
MATRIX_FILENAME = "feedback_table.pkl"
LEGACY_MATRIX_FILENAME = "feedback_matrix.pkl"
SERVER_PORT = 8765
FEEDBACK_PATTERN_COUNT = 3 ** WORD_LENGTH
FEEDBACK_DIGITS = {'X': 0, 'Y': 1, 'G': 2}


@lru_cache(maxsize=4)
def entropy_contributions(max_count: int) -> Tuple[float, ...]:
    return tuple(
        0.0 if count < 2 else count * math.log2(count)
        for count in range(max_count + 1)
    )

class VicSolver:
    def __init__(self, all_words: List[str], feedback_matrix):
        self.all_words = list(all_words)
        self.word_to_index = {word: index for index, word in enumerate(self.all_words)}
        if isinstance(feedback_matrix, dict):
            self.feedback_rows = build_feedback_table(self.all_words, feedback_matrix)
        else:
            self.feedback_rows = feedback_matrix

        if len(self.feedback_rows) != len(self.all_words):
            raise ValueError("Feedback table does not match the word list.")
        if any(len(row) != len(self.all_words) for row in self.feedback_rows):
            raise ValueError("Feedback table contains a row with the wrong length.")

        self.possible_indices = list(range(len(self.all_words)))
        self.possible_words = list(self.all_words)
        self.possible_flags = bytearray(b'\x01') * len(self.all_words)
        self.entropy_values = entropy_contributions(len(self.all_words))
        self.guess_count = 0

    def _calculate_entropy_for_index(self, guess_index: int) -> float:
        if not self.possible_indices:
            return 0.0

        total_count = len(self.possible_indices)
        feedback_counts = [0] * FEEDBACK_PATTERN_COUNT
        feedback_row = self.feedback_rows[guess_index]
        for target_index in self.possible_indices:
            feedback_counts[feedback_row[target_index]] += 1

        entropy = math.log2(total_count)
        for count in feedback_counts:
            entropy -= self.entropy_values[count] / total_count
        return entropy

    def _calculate_entropy(self, guess: str) -> float:
        guess_index = self.word_to_index.get(guess)
        if guess_index is not None:
            return self._calculate_entropy_for_index(guess_index)

        if not self.possible_indices:
            return 0.0

        feedback_groups = collections.Counter(
            get_feedback(guess, self.all_words[target_index])
            for target_index in self.possible_indices
        )
        total_count = len(self.possible_indices)
        return sum(
            (count / total_count) * math.log2(total_count / count)
            for count in feedback_groups.values()
        )

    def get_best_guess(self) -> str:
        if not self.possible_indices:
            return ""

        if len(self.possible_indices) == len(self.all_words) and PRECOMPUTED_FIRST_GUESS in self.word_to_index:
            return PRECOMPUTED_FIRST_GUESS

        if len(self.possible_indices) <= 2:
            return self.all_words[self.possible_indices[0]]

        def score_key(guess_index: int) -> Tuple[float, bool]:
            entropy = self._calculate_entropy_for_index(guess_index)
            is_possible = self.possible_flags[guess_index]
            return (entropy, is_possible)

        best_guess_index = max(range(len(self.all_words)), key=score_key)
        return self.all_words[best_guess_index]

    def apply_feedback(self, guess: str, feedback: str):
        if len(guess) != WORD_LENGTH or len(feedback) != WORD_LENGTH:
            return

        guess = guess.upper()
        feedback = feedback.upper()
        feedback_code = encode_feedback(feedback)
        guess_index = self.word_to_index.get(guess)

        if guess_index is None:
            self.possible_indices = [
                target_index
                for target_index in self.possible_indices
                if get_feedback(guess, self.all_words[target_index]) == feedback
            ]
        else:
            feedback_row = self.feedback_rows[guess_index]
            self.possible_indices = [
                target_index
                for target_index in self.possible_indices
                if feedback_row[target_index] == feedback_code
            ]

        self.possible_words = [self.all_words[index] for index in self.possible_indices]
        self.possible_flags = bytearray(len(self.all_words))
        for target_index in self.possible_indices:
            self.possible_flags[target_index] = 1
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


def encode_feedback(feedback: str) -> int:
    if len(feedback) != WORD_LENGTH:
        raise ValueError(f"Feedback must contain {WORD_LENGTH} symbols.")

    code = 0
    for symbol in feedback:
        try:
            digit = FEEDBACK_DIGITS[symbol]
        except KeyError as error:
            raise ValueError(f"Invalid feedback pattern: {feedback}") from error
        code = code * 3 + digit
    return code


def get_feedback_code(guess: str, target: str) -> int:
    target_counts = [0] * 26
    for character in target:
        target_counts[ord(character) - ord('A')] += 1

    feedback_digits = [0] * WORD_LENGTH
    for index in range(WORD_LENGTH):
        if guess[index] == target[index]:
            feedback_digits[index] = 2
            target_counts[ord(guess[index]) - ord('A')] -= 1

    for index in range(WORD_LENGTH):
        if feedback_digits[index] == 2:
            continue
        character_index = ord(guess[index]) - ord('A')
        if target_counts[character_index] > 0:
            feedback_digits[index] = 1
            target_counts[character_index] -= 1

    code = 0
    for digit in feedback_digits:
        code = code * 3 + digit
    return code


def compute_row_for_guess(guess: str, all_words: Tuple[str, ...]) -> bytes:
    return bytes(get_feedback_code(guess, target) for target in all_words)


def build_feedback_table(all_words: List[str], feedback_matrix: Dict[Tuple[str, str], str]):
    rows = []
    for guess in all_words:
        row = bytearray(len(all_words))
        for target_index, target in enumerate(all_words):
            feedback = feedback_matrix.get((guess, target))
            if feedback is None:
                raise ValueError(f"Missing feedback for {guess} vs {target}.")
            row[target_index] = encode_feedback(feedback)
        rows.append(bytes(row))
    return tuple(rows)


def save_feedback_table(filename: str, all_words: List[str], feedback_table) -> None:
    payload = {
        'version': 2,
        'words': tuple(all_words),
        'rows': tuple(feedback_table),
    }
    with open(filename, 'wb') as file:
        pickle.dump(payload, file, protocol=pickle.HIGHEST_PROTOCOL)


def load_feedback_table(filename: str, all_words: List[str]):
    with open(filename, 'rb') as file:
        payload = pickle.load(file)

    if not isinstance(payload, dict) or payload.get('version') != 2:
        raise ValueError(f"Unsupported feedback table format in '{filename}'.")
    if tuple(all_words) != tuple(payload.get('words', ())):
        raise ValueError("Feedback table was generated from a different word list.")
    return tuple(payload['rows'])

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
    feedback_table = []

    with concurrent.futures.ProcessPoolExecutor(max_workers=max_workers) as executor:
        worker_func = partial(compute_row_for_guess, all_words=tuple(all_words))
        chunksize = max(1, num_words // (max_workers * 4))
        results_iterator = executor.map(worker_func, all_words, chunksize=chunksize)
        
        for i, row_dict in enumerate(results_iterator):
            feedback_table.append(row_dict)
            progress = (i + 1) / num_words
            elapsed_time = time.time() - start_time
            sys.stdout.write(
                f"\r  Progress: [{int(progress * 30) * '='}>{(30 - int(progress * 30)) * ' '}] "
                f"{i + 1}/{num_words} ({progress:.1%}) | Elapsed: {elapsed_time:.1f}s"
            )
            sys.stdout.flush()

    total_time = time.time() - start_time
    print(f"\n\nComputation complete in {total_time:.2f} seconds.")

    print(f"Saving feedback table to '{MATRIX_FILENAME}'...")
    try:
        save_feedback_table(MATRIX_FILENAME, all_words, feedback_table)
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
        if os.path.exists(MATRIX_FILENAME):
            FEEDBACK_MATRIX = load_feedback_table(MATRIX_FILENAME, ALL_WORDS)
        elif os.path.exists(LEGACY_MATRIX_FILENAME):
            print(f"Converting legacy matrix '{LEGACY_MATRIX_FILENAME}'...")
            with open(LEGACY_MATRIX_FILENAME, 'rb') as file:
                legacy_matrix = pickle.load(file)
            FEEDBACK_MATRIX = build_feedback_table(ALL_WORDS, legacy_matrix)
            save_feedback_table(MATRIX_FILENAME, ALL_WORDS, FEEDBACK_MATRIX)
            print(f"Converted matrix saved as '{MATRIX_FILENAME}'.")
        else:
            raise FileNotFoundError(MATRIX_FILENAME)
    except FileNotFoundError:
        print(f"FATAL: Could not find feedback table '{MATRIX_FILENAME}'.", file=sys.stderr)
        print("Please run 'python solver.py --precompute' first.", file=sys.stderr)
        sys.exit(1)
    except Exception as e:
        print(f"FATAL: Could not load feedback table '{MATRIX_FILENAME}'. Error: {e}", file=sys.stderr)
        sys.exit(1)
    
    print(f"Data loaded: {len(ALL_WORDS)} words and {len(FEEDBACK_MATRIX)} feedback rows.")

class SolverHTTPHandler(BaseHTTPRequestHandler):
    def do_POST(self):
        try:
            content_length = int(self.headers.get('Content-Length', 0))
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

            start_time = time.time()
            solver = VicSolver(ALL_WORDS, FEEDBACK_MATRIX)
            for guess_data in guesses:
                word = guess_data.get('word', '').upper()
                feedback = guess_data.get('feedback', '')
                solver.apply_feedback(word, feedback)

            print(f"[Solver] {len(solver.possible_words)} possible words remain.")
            status = solver.get_status()
            elapsed_time = time.time() - start_time
            
            print(f"[Solver] Best guess: '{status['next_guess']}' (calculated in {elapsed_time:.3f}s)")
            
            response = {
                "next_guess": status['next_guess'],
                "possible_words_count": status['possible_words_count'],
                "options": status['options']
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
        pass

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