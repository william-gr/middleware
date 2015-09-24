import unittest
import sys

loader = unittest.TestLoader()
r = loader.discover('./')
results = unittest.TestResult()
results.buffer = True
r.run(results)

overall = results.wasSuccessful()

print '========================='
print "Total tests discovered:  " + str(r.countTestCases())
print "Total tests ran: " + str(results.testsRun)
print "Overall Result: " + str(overall)
print '========================='
if not overall:
    print '========================================='
    print "The Failed Tests reported these errors:"
    print '========================================='
    for error in results.failures:
	    print str(error[0]) + ': \n' + error[1]

#print results.errors