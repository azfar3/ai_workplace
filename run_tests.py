import unittest
import frappe

def run():
    loader = unittest.TestLoader()
    tests = loader.discover("/home/erp/frappe-v15/apps/ai_workplace/ai_workplace/tests", pattern="test_ai_orchestrator*.py")
    testRunner = unittest.runner.TextTestRunner(verbosity=2)
    testRunner.run(tests)
