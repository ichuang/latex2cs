import glob
from setuptools import setup

def findfiles(pat):
    #return [x[10:] for x in glob.glob('latex2cs/' + pat)]
    return [x for x in glob.glob('share/' + pat)]

data_files = [
    ('share/render', findfiles('render/*')),
    ('share/testtex', findfiles('testtex/*')),
    ('share/plastexpy', findfiles('plastexpy/*.py')),
    ]

with open("README.md", "r") as fh:
    long_description = fh.read()

# print "data_files = %s" % data_files

setup(
    name='latex2cs',
    version='0.0.1',
    author='I. Chuang',
    author_email='ichuang@mit.edu',
    packages=['latex2cs', 'latex2cs.test'],
    scripts=[],
    url='http://pypi.python.org/pypi/latex2cs/',
    license='LICENSE.txt',
    description='Converter from latex to catsoop markdown format',
    long_description=long_description,
    long_description_content_type="text/markdown",
    include_package_data=True,
    entry_points={
        'console_scripts': [
            'latex2cs = latex2cs.main:CommandLine',
            ],
        },
    install_requires=['latex2edx',
                      'path',
                      ],
    # note plasTeX needs to be version 2.1
    package_dir={'latex2cs': 'latex2cs'},
    #package_data={'latex2cs': ['render/*', 'testtex/*', 'plastexpy/*.py',
    #                            'python_lib/*.py', 'latex2cs.js',
    #                            'latex2cs.css']},
    # data_files = data_files,
    test_suite="latex2cs.test",
)
