[metadata]
name = waitress
version = 2.1.1
description = Waitress WSGI server
long_description = file: README.rst, CHANGES.txt
long_description_content_type = text/x-rst
keywords = waitress wsgi server http
license = ZPL 2.1
classifiers =
    Development Status :: 6 - Mature
    Environment :: Web Environment
    Intended Audience :: Developers
    License :: OSI Approved :: Zope Public License
    Programming Language :: Python
    Programming Language :: Python :: 3
    Programming Language :: Python :: 3.7
    Programming Language :: Python :: 3.8
    Programming Language :: Python :: 3.9
    Programming Language :: Python :: 3.10
    Programming Language :: Python :: Implementation :: CPython
    Programming Language :: Python :: Implementation :: PyPy
    Operating System :: OS Independent
    Topic :: Internet :: WWW/HTTP
    Topic :: Internet :: WWW/HTTP :: WSGI
url = https://github.com/Pylons/waitress
project_urls =
    Documentation = https://docs.pylonsproject.org/projects/waitress/en/latest/index.html
    Changelog = https://docs.pylonsproject.org/projects/waitress/en/latest/index.html#change-history
    Issue Tracker = https://github.com/Pylons/waitress/issues

author = Zope Foundation and Contributors
author_email = zope-dev@zope.org
maintainer = Pylons Project
maintainer_email = pylons-discuss@googlegroups.com

[options]
package_dir=
    =src
packages=find:
python_requires = >=3.7.0

[options.entry_points]
paste.server_runner =
    main = waitress:serve_paste
console_scripts =
    waitress-serve = waitress.runner:run

[options.packages.find]
where=src

[options.extras_require]
testing =
    pytest
    pytest-cover
    coverage>=5.0

docs =
    Sphinx>=1.8.1
    docutils
    pylons-sphinx-themes>=1.0.9

[tool:pytest]
python_files = test_*.py
# For the benefit of test_wasyncore.py
python_classes = Test*
testpaths =
    tests
addopts = --cov -W always
