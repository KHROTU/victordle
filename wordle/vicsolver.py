from typing import Dict, List, Tuple

WORD_LENGTH = 5

class VicSolver:
    def __init__(self, all_words: List[str], feedback_matrix: Dict[Tuple[str, str], str]):
        self.all_words = all_words
        self.feedback_matrix = feedback_matrix
        self.possible_words = list(self.all_words)
        self.guess_count = 0

    def _calculate_guess_score(self, guess: str) -> int:
        if not self.possible_words:
            return 0

        feedback_groups = {}
        for target_word in self.possible_words:
            feedback = self.feedback_matrix.get((guess, target_word), "")
            feedback_groups[feedback] = feedback_groups.get(feedback, 0) + 1

        return max(feedback_groups.values()) if feedback_groups else 0

    def get_best_guess(self) -> str:
        if not self.possible_words:
            return ""

        if len(self.possible_words) <= 2:
            return self.possible_words[0]

        candidates = self.all_words if len(self.possible_words) > 20 else self.possible_words

        best_guess = ""
        best_score = float('inf')

        scored_candidates = []
        for guess in candidates:
            score = self._calculate_guess_score(guess)
            is_possible_solution = guess in self.possible_words
            scored_candidates.append((score, not is_possible_solution, guess))
        
        # sort by score then by whether it's a possible solution (false comes first) then by word
        scored_candidates.sort()
        
        return scored_candidates[0][2] if scored_candidates else ""

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
            "possible_words": len(self.possible_words),
            "next_guess": next_guess,
            "options": self.possible_words[:10] if len(self.possible_words) <= 10 else []
        }