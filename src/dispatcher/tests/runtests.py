import unittest
import sys

loader = unittest.TestLoader()
r = loader.discover('./')
results = unittest.TestResult()

results.buffer = True
r.run(results)
overall = results.wasSuccessful()

print '============================='
print "Total tests discovered:  " + str(r.countTestCases())
print "Total tests ran: " + str(results.testsRun)
print 'Tests failed: ' + str(len(results.failures))
print 'Tests skipped: ' + str(len(results.skipped))
print "Overall Result: " + str(overall)
print '============================='
if not overall:
    print '========================================='
    print "ERRORS:\n"
    for error in results.errors:
        print str(error[0]) + ': '
        print '========================================='
        print  error[1]
        print '========================================='