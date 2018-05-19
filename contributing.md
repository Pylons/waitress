Contributing
============

All projects under the Pylons Projects, including this one, follow the guidelines established at [How to Contribute](https://pylonsproject.org/community-how-to-contribute.html) and [Coding Style and Standards](https://pylonsproject.org/community-coding-style-standards.html).


Get support
-----------

See [Get Support](https://pylonsproject.org/community-support.html). You are reading this document most likely because you want to *contribute* to the project and not *get support*.


Working on issues
-----------------

To respect both your time and ours, we emphasize the following points.

* We use the [Issue Tracker on GitHub](https://github.com/Pylons/waitress/issues) to discuss bugs, improvements, and feature requests. Search through existing issues before reporting a new one. Issues may be complex or wide-ranging. A discussion up front sets us all on the best path forward.
* Minor issues—such as spelling, grammar, and syntax—don't require discussion and a pull request is sufficient.
* After discussing the issue with maintainers and agreeing on a resolution, submit a pull request of your work. [GitHub Flow](https://guides.github.com/introduction/flow/index.html) describes the workflow process and why it's a good practice.


Git branches
------------

There is a single branch [master](https://github.com/Pylons/waitress/) on which development takes place and from which releases to PyPI are tagged. This is the default branch on GitHub.


Running tests and building documentation
----------------------------------------

We use [tox](https://tox.readthedocs.io/en/latest/) to automate test running, coverage, and building documentation across all supported Python versions.

To run everything configured in the `tox.ini` file:

    $ tox

To run tests on Python 2 and 3, and ensure full coverage, but exclude building of docs:

    $ tox -e py2-cover,py3-cover,coverage

To build the docs only:

    $ tox -e docs

See the `tox.ini` file for details.


Contributing documentation
--------------------------

*Note:* These instructions might not work for Windows users. Suggestions to improve the process for Windows users are welcome by submitting an issue or a pull request.

1.  Fork the repo on GitHub by clicking the [Fork] button.
2.  Clone your fork into a workspace on your local machine.

         cd ~/projects
         git clone git@github.com:<username>/waitress.git

3.  Add a git remote "upstream" for the cloned fork.

         git remote add upstream git@github.com:Pylons/waitress.git

4.  Set an environment variable to your virtual environment.

         # Mac and Linux
         $ export VENV=~/projects/waitress/env

         # Windows
         set VENV=c:\projects\waitress\env

5.  Try to build the docs in your workspace.

         # Mac and Linux
         $ make clean html SPHINXBUILD=$VENV/bin/sphinx-build

         # Windows
         c:\> make clean html SPHINXBUILD=%VENV%\bin\sphinx-build

     If successful, then you can make changes to the documentation. You can load the built documentation in the `/_build/html/` directory in a web browser.

6.  From this point forward, follow the typical [git workflow](https://help.github.com/articles/what-is-a-good-git-workflow/). Start by pulling from the upstream to get the most current changes.

         git pull upstream master

7.  Make a branch, make changes to the docs, and rebuild them as indicated in step 5.  To speed up the build process, you can omit `clean` from the above command to rebuild only those pages that depend on the files you have changed.

8.  Once you are satisfied with your changes and the documentation builds successfully without errors or warnings, then git commit and push them to your "origin" repository on GitHub.

         git commit -m "commit message"
         git push -u origin --all # first time only, subsequent can be just 'git push'.

9.  Create a [pull request](https://help.github.com/articles/using-pull-requests/).

10.  Repeat the process starting from Step 6.
