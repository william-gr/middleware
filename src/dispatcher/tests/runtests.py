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
print 'Errors reported: ' + str(len(results.errors))
print 'Tests skipped: ' + str(len(results.skipped))
print "Overall Result: " + str(overall)
print '============================='
if not overall:
    print '========================================='
    print "ERRORS:\n"
    print '========================================='
    for error in results.errors:
        print str(error[0]) + ': '
        print '========================================='
        print  error[1]
        print '========================================='
    print '========================================='
    print 'FAILURES'
    print '========================================='
    for failure in results.failures:
        print str(failure[0]) + ': '
        print '========================================='
        print  failure[1]
        print '========================================='

    
if not overall:
    exit(-1)
exit(0)    