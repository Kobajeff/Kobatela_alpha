import sys
import os
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import unittest
from transactions.alerts import log_unauthorized_attempt

class TestAlerts(unittest.TestCase):
    def test_log_unauthorized_attempt(self):
        # Teste si la fonction s'exécute correctement
        log_unauthorized_attempt("99999")
        self.assertTrue(True)  # Remplacez par une vérification de fichier journal si nécessaire

if __name__ == "__main__":
    unittest.main()

class TestBasic(unittest.TestCase):
    def test_always_passes(self):
        self.assertTrue(True)
