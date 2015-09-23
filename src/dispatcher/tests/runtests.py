import unittest
import sys

loader = unittest.TestLoader()
r = loader.discover('./')
results = unittest.TestResult()
r.run(results)

print 'Result is ' + str(results)
print "Tests ran " + str(results.testsRun)
print "Tests result: " + str(results.wasSuccessful())

