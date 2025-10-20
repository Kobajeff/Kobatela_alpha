import sys
import os
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import unittest

class TestSimple(unittest.TestCase):
    def test_example(self):
        self.assertTrue(True)

if __name__ == "__main__":
    unittest.main()
