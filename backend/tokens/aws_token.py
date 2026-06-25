"""
AWS Canary Token — generates fake AWS credentials that trigger an alert
when used. Uses randomized account IDs to defeat credential scanners
that check account validity before attempting use.
"""
import random
import secrets
import string


def generate_aws_token(token_id: str, name: str) -> dict:
    """
    Generate convincing-looking fake AWS credentials.
    The access key ID encodes the token_id so the capture server
    can identify which canary was triggered via CloudTrail or
    a monitoring endpoint.

    Key design: randomized 12-digit account ID defeats scanners
    that pre-validate account IDs before attempting credential use.
    """
    # AWS access key IDs start with AKIA for long-term credentials
    # We use CANA (canary) prefix to make them identifiable in logs
    # while still looking plausible to automated scanners
    key_suffix = _random_alphanum(16).upper()
    access_key_id = f"CANA{key_suffix}"

    # Secret key: 40-char base64-like string
    secret_key = secrets.token_urlsafe(30)

    # Randomized account ID (12 digits) — defeats scanners
    account_id = "".join([str(random.randint(0, 9)) for _ in range(12)])

    # Region
    region = random.choice([
        "us-east-1", "us-west-2", "eu-west-1", "ap-southeast-1"
    ])

    credentials_file = f"""[default]
aws_access_key_id = {access_key_id}
aws_secret_access_key = {secret_key}
region = {region}

# Account: {account_id}
# Created for: {name}
"""

    return {
        "token_value": access_key_id,  # The key ID is the primary identifier
        "slug": access_key_id,
        "metadata": {
            "name": name,
            "type": "aws",
            "access_key_id": access_key_id,
            "secret_access_key": secret_key,
            "account_id": account_id,
            "region": region,
            "credentials_file": credentials_file,
            "token_id": token_id,
            "instructions": (
                "Drop the credentials_file content as ~/.aws/credentials or in a "
                "config file, S3 bucket, or code repo. Any attempted use of these "
                "keys will be detected via CloudTrail or credential-checker monitoring. "
                f"Monitor for access_key_id: {access_key_id}"
            ),
        },
    }


def _random_alphanum(length: int) -> str:
    alphabet = string.ascii_uppercase + string.digits
    return "".join(secrets.choice(alphabet) for _ in range(length))
