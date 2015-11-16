from setuptools import setup


install_requires = [
    'jsonschema',
    'freenas.utils',
    'paramiko',
    'six',
    'ws4py',
]

setup(
    name='dispatcher-client',
    version='10.0',
    description='Dispatcher client library',
    packages=['dispatcher'],
    license='BSD',
    platforms='any',
    classifiers=[
        'Development Status :: 4 - Beta',
        'Intended Audience :: Developers',
        'License :: OSI Approved :: BSD License',
        'Programming Language :: Python',
        'Programming Language :: Python :: 2.7',
        'Programming Language :: Python :: 3',
    ],
    install_requires=install_requires,
)
