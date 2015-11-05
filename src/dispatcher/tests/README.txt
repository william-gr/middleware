
Run tests from directory: middleware/src/dispatcher/tests
PYTHONPATH should be set to ../client/python:../../py-fnutils
TESTHOST should point to the server IP the tests are running on: example: 10.5.0.160

Packages to install prior to running the tests:

 sudo pkg install py27-jsonschema-2.4.0
 sudo pkg install py27-enum34-1.0.4
 sudo pkg install py27-dateutil-2.3
 sudo pkg install py27-ws4py-0.3.4
 sudo pkg install py27-HTMLgen-2.2.2
 sudo pkg install py27-paramiko-1.15.2
 

To run individual tests:
python <name of the python test file>: python test_services.py

To run all the test modules:
python runtests.py

To run one test module:

python test_storage.py

To run only one function in one module, for example:

python test_storage.py VolumeTest.test_create_volume_auto_stripe


For development: The scemas, tasks, rpc calls, etc are accessible from the GUI of the freeNAS 10 running server: 

To check the tasks: http://10.5.0.160:8180/apidoc/tasks
Schemas: http://10.5.0.160:8180/apidoc/schemas
rpc calls http://10.5.0.160:8180/rpc
 
