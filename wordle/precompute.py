import collections
import concurrent.futures
import os
import pickle
import sys
import time
from functools import partial
from typing import Dict, List, Tuple

WORD_LENGTH = 5
WORD_LIST_FILENAME = "words.txt"
MATRIX_FILENAME = "feedback_matrix.pkl"

try:
    MAX_WORKERS = os.cpu_count() or 4
except NotImplementedError:
    MAX_WORKERS = 4


def load_words(filename: str) -> List[str]:
    try:
        script_dir = os.path.dirname(os.path.realpath(__file__))
    except NameError:
        script_dir = os.getcwd()
    filepath = os.path.join(script_dir, filename)

    if not os.path.exists(filepath):
        print(f"Error: Word list file '{filepath}' not found.", file=sys.stderr)
        sys.exit(1)

    words = set()
    try:
        with open(filepath, 'r') as f:
            for line in f:
                word = line.strip().upper()
                if len(word) == WORD_LENGTH and word.isalpha():
                    words.add(word)
    except Exception as e:
        print(f"Error reading word list file '{filepath}': {e}", file=sys.stderr)
        sys.exit(1)

    if not words:
        print(f"Error: No valid {WORD_LENGTH}-letter words found in '{filepath}'.", file=sys.stderr)
        sys.exit(1)

    return sorted(list(words))


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
    row_dict = {}
    for target in all_words:
        row_dict[(guess, target)] = get_feedback(guess, target)
    return row_dict


def precompute_and_save():
    script_dir = os.path.dirname(os.path.realpath(__file__))
    matrix_filepath = os.path.join(script_dir, MATRIX_FILENAME)

    print("Starting pre-computation of the feedback matrix.")
    if os.path.exists(matrix_filepath):
        print(f"'{MATRIX_FILENAME}' already exists. Skipping.")
        return

    all_words = load_words(WORD_LIST_FILENAME)
    num_words = len(all_words)
    total_calculations = num_words * num_words

    print(f"Loaded {num_words} words.")
    print(f"Preparing to compute {total_calculations:,} feedback results using up to {MAX_WORKERS} processes.")
    print("This may take several minutes...")

    start_time = time.time()
    feedback_matrix = {}

    with concurrent.futures.ProcessPoolExecutor(max_workers=MAX_WORKERS) as executor:
        worker_func = partial(compute_row_for_guess, all_words=tuple(all_words))
        results_iterator = executor.map(worker_func, all_words, chunksize=num_words // (MAX_WORKERS * 4) + 1)
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
        with open(matrix_filepath, 'wb') as f:
            pickle.dump(feedback_matrix, f, protocol=pickle.HIGHEST_PROTOCOL)
    except Exception as e:
        print(f"Error saving file: {e}", file=sys.stderr)
        sys.exit(1)

    file_size = os.path.getsize(matrix_filepath) / (1024 * 1024)
    print(f"Successfully saved. File size: {file_size:.2f} MB")


if __name__ == "__main__":
    precompute_and_save()