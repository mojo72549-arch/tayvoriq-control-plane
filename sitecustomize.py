"""Keep control-plane Python startup deterministic before implementation deps exist.

The implementation repository is added to PYTHONPATH for production execution, but
its startup hooks may import third-party packages that are installed only later in
the job. Providing this no-op control-plane sitecustomize prevents those optional
implementation hooks from contaminating early request/manifest commands.
"""
