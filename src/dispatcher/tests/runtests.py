import unittest
import sys
import os
import inspect
import traceback
import time
import subprocess

###############
# PYTHOPATH
###############
testdir = os.getcwd()

topdir = subprocess.check_output('git rev-parse --show-toplevel',shell=True).rstrip('\n')
topdir = os.path.normpath(topdir)
sys.path.append(os.path.join(topdir, 'src/dispatcher/client/python'))
sys.path.append(os.path.join(topdir, 'src/py-fnutils'))

loader = unittest.TestLoader()
r = loader.discover('./')

results = unittest.TestResult()

# obtain all tests list
# TODO: there is a better way
complete_list = []


for suite in r._tests:
    for tests in suite._tests:
        if isinstance(tests, list):
            for unit in tests:
                complete_list.append(unit)
        
        elif isinstance(tests, unittest.TestSuite):
            for t in tests._tests:
                complete_list.append(t)

r.run(results)
overall = results.wasSuccessful()


# OUTPUT
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

print header(r, results)


#==========================
# HTML 
#====================
import HTMLgen

failed = {}
errors = {}
skipped = {}

# HTML LOG DIRECTORY
if os.getenv("HTML_LOGS"):
    logdir = os.getenv("HTML_LOGS")
else:    
    logdir = ('htmllogs')
if not os.path.isdir(logdir):
    os.mkdir(logdir)

##############
def html_output(results, struct):
    '''
    stack traces
    '''
    for info in results:
        struct[info[0].id()]=info
        doc = HTMLgen.SimpleDocument(title=info[0])
        make_header(info[0].id(), doc)
        
        for line in info[1].split('\n'):
            #print line
            text = HTMLgen.Text(line)
            doc.append(HTMLgen.Paragraph(text))
        doc.write(os.path.join(logdir, info[0].id()+'.html'))

def make_header(info, doc):
    '''
    Report header
    '''
    print info
    text = HTMLgen.Paragraph('Time : %s' % time.strftime('%c'))
    doc.append(text)
    text = HTMLgen.Paragraph('Server: %s' % os.getenv('TESTHOST'))
    doc.append(text)
    text = HTMLgen.Paragraph('Test Module/Class/Name: %s' % info)
    doc.append(text)
    text = HTMLgen.Paragraph('###################')
    doc.append(text)

    return doc



def append_to_table(table, test_id, group, text='FAILED'):
    '''
    hyperlink Reference to error
    '''
    f = group[test_id]
    filename = test_id + '.html'
    href = HTMLgen.Href(filename, HTMLgen.Text(text))
    l = [f[0].id().split('.')[0], f[0].id().split('.')[1], f[0].id().split('.')[2], href, '']
    t.body.append(l)


# create html file per failure
html_output(results.errors, errors)
html_output(results.failures, failed)
html_output(results.skipped, skipped)

# Write the files to html for referral
def testfiles_to_html(complete_list, html_root):
    '''
    Construct {test_id: [source file, html file] } structure
    '''
    
    units = {}
    modules = []
    html_root = os.path.realpath(html_root)

    for test in complete_list:
        test_id = test.id()
        units[test_id] = []
        (module, cls, method) = test_id.split('.')
        testfile = os.path.realpath(module + '.py')
        htmlfile = os.path.realpath(os.path.join(html_root, module + '.py.html'))
        units[test_id].append(testfile)
        units[test_id].append(htmlfile)
        modules.append(testfile)
        
    modules = set(modules)
    for mod in modules:
        pth = txt2html(mod, html_root)
    return units

def txt2html(py_path, html_root):
    newpath = os.path.join(html_root, os.path.split(py_path)[1] + '.html')
    command = 'txt2html --outfile ' + newpath + ' ' + py_path
    res = os.system(command)
    if res:
        raise Exception, "Could not create html file"
    return newpath


# HTML STRUCTS
# top report html file
doc = HTMLgen.SimpleDocument(title="index")
text = HTMLgen.Text('Test Date: ' + str(time.strftime("%c")))
doc.append(HTMLgen.Paragraph(text))


# table of tests
t = HTMLgen.Table('Unit Test Run Results')
h = ['Test Locaion/Module', 'Test Class/Group', 'Test Method Name', 'Test Result', 'Source File']
t.heading = h

# Bookkeeping structure
units = testfiles_to_html(complete_list, logdir)

# fill in the table
try:
  for test in complete_list:
    test_id = test.id()
    htm_log = units[test_id][1]
    src = units[test_id][0]
    srcref = HTMLgen.Href(os.path.split(htm_log)[1], HTMLgen.Text(src))        

    if test_id not in failed.keys() + errors.keys() + skipped.keys():
        l = [test_id.split('.')[0], test_id.split('.')[1], test_id.split('.')[2], 'OK', srcref]  
        t.body.append(l)
        
    elif test_id in failed.keys():
        f = failed[test_id]
        filename = test_id + '.html'
        href = HTMLgen.Href(filename, HTMLgen.Text('FAILED'))
        l = [f[0].id().split('.')[0], f[0].id().split('.')[1], f[0].id().split('.')[2], href, srcref]
        t.body.append(l)

    elif test.id() in errors.keys():
        f = errors[test_id]
        filename = test_id + '.html'
        href = HTMLgen.Href(filename, HTMLgen.Text('ERROR'))
        l = [f[0].id().split('.')[0], f[0].id().split('.')[1], f[0].id().split('.')[2], href, srcref]
        t.body.append(l)

    elif test.id() in skipped.keys():
        f = skipped[test_id]
        filename = test_id + '.html'
        href = HTMLgen.Href(filename, HTMLgen.Text('SKIPPED'))
        l = [f[0].id().split('.')[0], f[0].id().split('.')[1], f[0].id().split('.')[2], href, srcref]
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
