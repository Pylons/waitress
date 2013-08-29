##############################################################################
#
# Copyright (c) 2006 Zope Foundation and Contributors.
# All Rights Reserved.
#
# This software is subject to the provisions of the Zope Public License,
# Version 2.1 (ZPL).  A copy of the ZPL should accompany this distribution.
# THIS SOFTWARE IS PROVIDED "AS IS" AND ANY AND ALL EXPRESS OR IMPLIED
# WARRANTIES ARE DISCLAIMED, INCLUDING, BUT NOT LIMITED TO, THE IMPLIED
# WARRANTIES OF TITLE, MERCHANTABILITY, AGAINST INFRINGEMENT, AND FITNESS
# FOR A PARTICULAR PURPOSE.
#
##############################################################################
import os
import sys
from setuptools import setup, find_packages

here = os.path.abspath(os.path.dirname(__file__))
try:
    README = open(os.path.join(here, 'README.rst')).read()
    CHANGES = open(os.path.join(here, 'CHANGES.txt')).read()
except IOError:
    README = CHANGES = ''

docs_extras = [
    'Sphinx',
    'docutils',
]

testing_extras = [
    'nose',
    'coverage',
]

if sys.version_info[:2] == (2, 6):
    testing_extras.append('unittest2')

setup(
    name='waitress',
    version='0.8.7',
    author='Zope Foundation and Contributors',
    author_email='zope-dev@zope.org',
    maintainer="Chris McDonough",
    maintainer_email="chrism@plope.com",
    description='Waitress WSGI server',
    long_description=README + '\n\n' + CHANGES,
    license='ZPL 2.1',
    keywords='waitress wsgi server http',
    classifiers=[
        'Development Status :: 5 - Production/Stable',
        'Environment :: Web Environment',
        'Intended Audience :: Developers',
        'License :: OSI Approved :: Zope Public License',
        'Programming Language :: Python',
        'Programming Language :: Python :: 2',
        'Programming Language :: Python :: 2.6',
        'Programming Language :: Python :: 2.7',
        'Programming Language :: Python :: 3',
        'Programming Language :: Python :: 3.2',
        'Programming Language :: Python :: 3.3',
        "Programming Language :: Python :: Implementation :: CPython",
        "Programming Language :: Python :: Implementation :: PyPy",
        'Natural Language :: English',
        'Operating System :: OS Independent',
        'Topic :: Internet :: WWW/HTTP',
    ],
    url='https://github.com/Pylons/waitress',
    packages=find_packages(),
    install_requires=[
        'setuptools',
    ],
    extras_require={
        'testing': testing_extras,
        'docs': docs_extras,
    },
    include_package_data=True,
    test_suite='waitress',
    zip_safe=False,
    entry_points="""
    [paste.server_runner]
    main = waitress:serve_paste
    [console_scripts]
    waitress-serve = waitress.runner:run
    """
)
