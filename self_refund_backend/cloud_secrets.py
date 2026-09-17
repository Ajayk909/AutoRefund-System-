"""
Write plaintext values into AWS Secrets Manager without ever logging them.

Used only by one-off cloud tasks (seed.py's generated admin password,
manage_tenancy.py's issue-staging-key). boto3 is imported lazily so local
development and tests never need it installed.
"""


def store_secret(secret_name, value, client=None):
    """Create or update ``secret_name`` with ``value``. Never print/log ``value``."""
    if client is None:
        import boto3
        client = boto3.client("secretsmanager")
    try:
        client.put_secret_value(SecretId=secret_name, SecretString=value)
    except client.exceptions.ResourceNotFoundException:
        client.create_secret(Name=secret_name, SecretString=value)
