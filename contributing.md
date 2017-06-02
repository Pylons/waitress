Contributing
============

All projects under the Pylons Projects, including this one, follow the
guidelines established at [How to
Contribute](http://www.pylonsproject.org/community/how-to-contribute) and
[Coding Style and
Standards](http://docs.pylonsproject.org/en/latest/community/codestyle.html).

You can contribute to this project in several ways.

* [File an Issue on GitHub](https://github.com/Pylons/waitress/issues)
* Fork this project and create a branch with your suggested change. When ready,
  submit a pull request for consideration. [GitHub
  Flow](https://guides.github.com/introduction/flow/index.html) describes the
  workflow process and why it's a good practice.
* Join the IRC channel [#pyramid](https://webchat.freenode.net/?channels=pyramid) on irc.freenode.net.


Git Branches
------------
There is a single branch [master](https://github.com/Pylons/waitress/) on which development takes place and from which releases to PyPI are tagged. This is the default branch on GitHub.


Running Tests
-------------

*Note:* This section needs better instructions.

Run `tox` from within your checkout. This will run the tests across all
supported systems and attempt to build the docs.

To run the tests for Python 2.x only:

    $ tox py2-cover

To build the docs for Python 3.x only:

    $ tox py3-docs

See the `tox.ini` file for details.


Building documentation for a Pylons Project project
---------------------------------------------------

*Note:* These instructions might not work for Windows users. Suggestions to
improve the process for Windows users are welcome by submitting an issue or a
pull request.

1.  Fork the repo on GitHub by clicking the [Fork] button.
2.  Clone your fork into a workspace on your local machine.

         git clone git@github.com:<username>/waitress.git

3.  Add a git remote "upstream" for the cloned fork.

         git remote add upstream git@github.com:Pylons/waitress.git

4.  Set an environment variable to your virtual environment.

         # Mac and Linux
         $ export VENV=~/hack-on-waitress/env

         # Windows
         set VENV=c:\hack-on-waitress\env

5.  Try to build the docs in your workspace.

         # Mac and Linux
         $ make clean html SPHINXBUILD=$VENV/bin/sphinx-build

         # Windows
         c:\> make clean html SPHINXBUILD=%VENV%\bin\sphinx-build

     If successful, then you can make changes to the documentation. You can
     load the built documentation in the `/_build/html/` directory in a web
     browser.

6.  From this point forward, follow the typical [git
    workflow](https://help.github.com/articles/what-is-a-good-git-workflow/).
    Start by pulling from the upstream to get the most current changes.

         git pull upstream master

7.  Make a branch, make changes to the docs, and rebuild them as indicated in
    step 5.  To speed up the build process, you can omit `clean` from the above
    command to rebuild only those pages that depend on the files you have
    changed.

8.  Once you are satisfied with your changes and the documentation builds
    successfully without errors or warnings, then git commit and push them to
    your "origin" repository on GitHub.

         git commit -m "commit message"
         git push -u origin --all # first time only, subsequent can be just 'git push'.

9.  Create a [pull request](https://help.github.com/articles/using-pull-requests/).

10.  Repeat the process starting from Step 6.