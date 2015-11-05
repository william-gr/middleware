import unittest
import sys
import os

loader = unittest.TestLoader()
r = loader.discover('./')

results = unittest.TestResult()

# obtain all tests list
# TODO: there is a better way for sure
complete_list = []
for suite in r._tests:
    #print 'r._tests test ' + str(suite.__dict__)
    for tests in suite._tests:
        #print 'test in f._tests ' + str(i)
        for unit in tests:
            complete_list.append(unit)
            

r.run(results)
overall = results.wasSuccessful()

# OUTPUT
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
    print "ERRORS:"
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

#==========================
# HTML
#====================
import HTMLgen

failed = {}
errors = {}

logdir = ('test_htmllogs')
if not os.path.isdir(logdir):
    os.mkdir(logdir)

# create html file per failure
for info in results.failures:
    failed[info[0].id()]=info
    doc = HTMLgen.SimpleDocument(title=info[0])
    for line in info[1].split('\n'):
        text = HTMLgen.Text(line)
        doc.append(HTMLgen.Paragraph(text))
    doc.write(os.path.join(logdir, info[0].id()+'.html'))

# create html file per error
for info in results.errors:
    errors[info[0].id()] = info
    doc = HTMLgen.SimpleDocument(title=info[0])
    for line in info[1].split('\n'):
        text = HTMLgen.Text(line)
        doc.append(HTMLgen.Paragraph(text))
    doc.write(os.path.join(logdir, info[0].id()+'.html'))

# top report html file
doc = HTMLgen.SimpleDocument(title="index")

# table of tests
t = HTMLgen.Table('Unit Test Run Results')
h = ['Module', 'Class', 'Method', 'Result']
t.heading = h

# fill in the table
for test in complete_list:
    test_id = test.id()

    if test.id() not in failed.keys() + errors.keys():
        l = [test_id.split('.')[0], test_id.split('.')[1], test_id.split('.')[2], '']  
        t.body.append(l)
        
    elif test.id() in failed.keys():
        test_id = test.id()
        f = failed[test_id]
        filename = test_id + '.html'
        href = HTMLgen.Href(filename, HTMLgen.Text('FAILED'))
        l = [f[0].id().split('.')[0], f[0].id().split('.')[1], f[0].id().split('.')[2], href]
        t.body.append(l)

    elif test.id() in errors.keys():
        f = errors[test.id()]
        filename = test.id() + '.html'
        href = HTMLgen.Href(filename, HTMLgen.Text('ERROR'))
        l = [f[0].id().split('.')[0], f[0].id().split('.')[1], f[0].id().split('.')[2], href]
        t.body.append(l)
    
    else:
        print "ERROR: " + test.id() + " is not accounted for, fix the bug"

doc.append(t)



# save top table
doc.write(os.path.join(logdir, "test_report.html"))

###################################
# EXIT
#################################
if not overall:
    exit(-1)
exit(0)    
