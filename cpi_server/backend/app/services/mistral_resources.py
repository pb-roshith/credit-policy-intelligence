"""Validate workspace-scoped resources without hiding provider failures."""
from mistralai.client.errors import SDKError


def resource_exists(get_resource, **identifier):
    try:
        get_resource(**identifier)
        return True
    except SDKError as error:
        if error.status_code == 404:
            return False
        # Authentication, billing and transient failures must not create copies.
        raise
