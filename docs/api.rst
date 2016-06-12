.. _waitress_api:

:mod:`waitress` API
---------------------------

.. module:: waitress

.. function:: serve(app, listen='0.0.0.0:8080', unix_socket=None, unix_socket_perms='600', threads=4, url_scheme='http', url_prefix='', ident='waitress', backlog=1204, recv_bytes=8192, send_bytes=18000, outbuf_overflow=104856, inbuf_overflow=52488, connection_limit=1000, cleanup_interval=30, channel_timeout=120, log_socket_errors=True, max_request_header_size=262144, max_request_body_size=1073741824, expose_tracebacks=False)

     See :ref:`arguments` for more information.
