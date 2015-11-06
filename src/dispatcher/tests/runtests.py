import unittest
import sys
import os
import inspect
import traceback

def getTestBody(method_pypath):
    return inspect.getsource(method_pypath).split()


loader = unittest.TestLoader()
r = loader.discover('./')

results = unittest.TestResult()

# obtain all tests list
# TODO: there is a better way
complete_list = []


for suite in r._tests:
    #print 'Test in suite ' + str(suite.__dict__)
    for tests in suite._tests:
        #print dir(tests)
        #print 'Type of the class in suite ' + str(type(tests))
        if isinstance(tests, list):
            for unit in tests:
                #print type(unit)
                complete_list.append(unit)
        else:
            for t in tests._tests:
                #print dir(t)
                #print t._testMethodDoc()
                complete_list.append(t)

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

def header(r, results):
    overall = results.wasSuccessful()
    output = 'Total tests discovered:  ' + str(r.countTestCases()) + os.linesep
    output += 'Total tests ran: ' + str(results.testsRun) + os.linesep
    output += 'Tests failed: ' + str(len(results.failures)) + os.linesep
    output += 'Errors reported: ' + str(len(results.errors)) + os.linesep
    output += 'Tests skipped: ' + str(len(results.skipped)) + os.linesep
    output += "Overall Result: " + str(overall) + os.linesep
    output += '=============================' + os.linesep
    if not overall:
        output += '=========================================' + os.linesep
        output += "ERRORS:" + os.linesep
        output += '=========================================' + os.linesep
        for error in results.errors:
            output += str(error[0]) + ': ' + os.linesep
            output += '=========================================' + os.linesep
            output += str(error[1]) + os.linesep
            output += '=========================================' + os.linesep
    output += '=========================================' + os.linesep
    output += 'FAILURES' + os.linesep
    output += '=========================================' + os.linesep
    for failure in results.failures:
        output += str(failure[0]) + ': ' + os.linesep
        output += '=========================================' + os.linesep
        output +=  str(failure[1]) + os.linesep
        output += '=========================================' + os.linesep    
    return output

#==========================
# HTML 
#====================
import HTMLgen

failed = {}
errors = {}
skipped = {}

logdir = ('htmllogs')
if not os.path.isdir(logdir):
    os.mkdir(logdir)

##############
def html_output(results, struct):
    for info in results:
        struct[info[0].id()]=info
        doc = HTMLgen.SimpleDocument(title=info[0])
        make_header(info[0].id(), doc)

        for line in info[1].split('\n'):
            text = HTMLgen.Text(line)
            doc.append(HTMLgen.Paragraph(text))
        doc.write(os.path.join(logdir, info[0].id()+'.html'))

def make_header(info, doc):

    mod = str(info.split('.')[0])
    
    obj = __import__(mod)
    print dir(obj)
    #import mod
    name = info
    #print name
    body = inspect.getsourcelines(obj)
    #print body 
    #(name, suffix, mode, mtype)  = inspect.getmoduleinfo(filename)
    #print name, suffix, mode, mtype

def append_to_table(table, test_id, group, text='FAILED'):
    f = group[test_id]
    filename = test_id + '.html'
    href = HTMLgen.Href(filename, HTMLgen.Text(text))
    l = [f[0].id().split('.')[0], f[0].id().split('.')[1], f[0].id().split('.')[2], href, '']
    t.body.append(l)

def file_to_html(f_path, html_root):
    '''
    Generates html file
    from a text file
    '''
    doc = HTMLgen.SimpleDocument(title=f_path)
    lst = HTMLgen.List()
    if os.path.exists(f_path):
        for line in open(f_path, 'r').readlines():
            lst.append(line)
    doc.append(lst)
    new_path = os.path.join(html_root, os.path.split(f_path)[1] + '.html')
    doc.write(new_path) 
    return os.path.join(new_path)       


# create html file per failure
html_output(results.errors, errors)
html_output(results.failures, failed)
html_output(results.skipped, skipped)

# Write the files to html for referral
def testfiles_to_html(complete_list, html_root):
    '''
    Constructs test unit-html file structure
    '''
    modules = []
    units = {}
    for test in complete_list:
        test_id = test.id()
        (module, cls, method) = test_id.split('.')
        testfile = os.path.realpath(module + '.py')
        modules.append(testfile)
        
        
    module_list = set(modules)
    for mod in module_list:
        file_to_html(mod, html_root)




# top report html file
doc = HTMLgen.SimpleDocument(title="index")

# table of tests
t = HTMLgen.Table('Unit Test Run Results')
h = ['Module', 'Class', 'Method', 'Result', 'Code']
t.heading = h

# fill in the table
try:
  for test in complete_list:
    test_id = test.id()
    #(module, cls, method) = test_id.split('.')
    #testfile = os.path.realpath(module + '.py')
    #print testfile

    if test_id not in failed.keys() + errors.keys() + skipped.keys():
        l = [test_id.split('.')[0], test_id.split('.')[1], test_id.split('.')[2], 'OK', '']  
        t.body.append(l)
        
    elif test_id in failed.keys():
        #test_id = test.id()
        f = failed[test_id]
        filename = test_id + '.html'
        href = HTMLgen.Href(filename, HTMLgen.Text('FAILED'))
        l = [f[0].id().split('.')[0], f[0].id().split('.')[1], f[0].id().split('.')[2], href, '']
        t.body.append(l)

    elif test.id() in errors.keys():
        f = errors[test_id]
        filename = test_id + '.html'
        href = HTMLgen.Href(filename, HTMLgen.Text('ERROR'))
        l = [f[0].id().split('.')[0], f[0].id().split('.')[1], f[0].id().split('.')[2], href, '']
        t.body.append(l)

    elif test.id() in skipped.keys():
        f = skipped[test_id]
        filename = test_id + '.html'
        href = HTMLgen.Href(filename, HTMLgen.Text('SKIPPED'))
        l = [f[0].id().split('.')[0], f[0].id().split('.')[1], f[0].id().split('.')[2], href, '']
        t.body.append(l)    
    
    else:
        print "ERROR: " + test.id() + " is not accounted for, fix the bug"

  doc.append(t)



  # save top table
  doc.write(os.path.join(logdir, "test_report.html"))
except Exception, data:
    import traceback
    traceback.print_exc()
    print data
###################################
# EXIT
#################################
if not overall:
    exit(-1)
exit(0)    
