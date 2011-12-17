FTP Framework

  This file contains documentation on the FTP server
  framework.

  The core server is implemented in server.py. This relies on a
  file-system abstraction, defined in zope.server.interfaces.py.

  The publisher module provides the connection to the object
  publsihing system by providing a file-system implementation that
  delegates file-system operations to objects through the publisher.
