import json
import sys
import os
import pickle
from http.server import HTTPServer, BaseHTTPRequestHandler
from vicsolver import VicSolver

WORD_LIST_FILENAME = "words.txt"
MATRIX_FILENAME = "feedback_matrix.pkl"
WORD_LENGTH = 5

ALL_WORDS = []
FEEDBACK_MATRIX = {}

def _load_all_data():
    global ALL_WORDS, FEEDBACK_MATRIX
    try:
        script_dir = os.path.dirname(os.path.realpath(__file__))
    except NameError:
        script_dir = os.getcwd()

    try:
        word_filepath = os.path.join(script_dir, WORD_LIST_FILENAME)
        with open(word_filepath, 'r') as f:
            words = {
                line.strip().upper()
                for line in f
                if len(line.strip()) == WORD_LENGTH and line.strip().isalpha()
            }
        ALL_WORDS = sorted(list(words))
    except Exception as e:
        print(f"FATAL: Could not load word list '{WORD_LIST_FILENAME}'. Error: {e}", file=sys.stderr)
        sys.exit(1)

    try:
        matrix_filepath = os.path.join(script_dir, MATRIX_FILENAME)
        with open(matrix_filepath, 'rb') as f:
            FEEDBACK_MATRIX = pickle.load(f)
    except Exception as e:
        print(f"FATAL: Could not load matrix '{MATRIX_FILENAME}'. Error: {e}", file=sys.stderr)
        print("Please ensure 'feedback_matrix.pkl' exists and was generated correctly.", file=sys.stderr)
        sys.exit(1)

    if not ALL_WORDS or not FEEDBACK_MATRIX:
        print("FATAL: Data loading resulted in empty lists or dictionaries.", file=sys.stderr)
        sys.exit(1)

    print(f"Data loaded successfully: {len(ALL_WORDS)} words and {len(FEEDBACK_MATRIX)} matrix entries.")


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
                if len(word) == 5 and len(feedback) == 5 and '?' not in feedback:
                    solver.apply_feedback(word, feedback)

            print(f"[Solver] Applied feedback. {len(solver.possible_words)} possible words remain.")
            status = solver.get_status()
            print(f"[Solver] Calculated next best guess: '{status['next_guess']}'")

            response = {
                "next_guess": status['next_guess'],
                "possible_words": status['possible_words']
            }
            print(f"[Response] Sending to client: {response}")
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

class VictordleAutomation:
    def __init__(self, port=8765):
        self.port = port
        self.server = None

    def start_server(self):
        try:
            self.server = HTTPServer(('localhost', self.port), SolverHTTPHandler)
            print(f"Server started on http://localhost:{self.port}")
            print("Ready for Victordle userscript. Press Ctrl+C to exit.")
            self.server.serve_forever()
        except OSError:
            print(f"Error: Port {self.port} is already in use.", file=sys.stderr)
        except Exception as e:
            print(f"Error starting server: {e}", file=sys.stderr)

    def run(self):
        print("--- Victordle Automation Server ---")
        try:
            self.start_server()
        except KeyboardInterrupt:
            print("\nShutting down server.")
        finally:
            if self.server:
                self.server.server_close()
            print("Server stopped.")

def main():
    _load_all_data()
    automation = VictordleAutomation()
    automation.run()

if __name__ == "__main__":
    main()