import os
import json
import time
import requests
from kubernetes import client, config

# Load environment variables
CLUSTER_NAME = os.getenv("CLUSTER_NAME", "unknown-cluster")
API_URL = os.getenv("API_URL", "http://localhost:5000/ingest")
CHECK_INTERVAL = int(os.getenv("CHECK_INTERVAL", 60))

# Load Kubernetes configuration
config.load_incluster_config()
core_v1 = client.CoreV1Api()


def get_tls_secrets():
    """Fetch TLS secrets from all namespaces."""
    secrets_data = []
    secrets = core_v1.list_secret_for_all_namespaces().items

    for secret in secrets:
        if secret.type == "kubernetes.io/tls":
            namespace = secret.metadata.namespace
            name = secret.metadata.name
            creation_date = secret.metadata.creation_timestamp.isoformat()

            # Extract certificate details
            cert_data = secret.data.get("tls.crt")
            if not cert_data:
                continue

            # Decode and parse the certificate
            try:
                from cryptography import x509
                from cryptography.hazmat.primitives import serialization
                import base64

                cert_bytes = base64.b64decode(cert_data)
                cert = x509.load_pem_x509_certificate(cert_bytes)

                cn = cert.subject.rfc4514_string()
                sans = [name.value for name in cert.extensions.get_extension_for_class(
                    x509.SubjectAlternativeName).value] if cert.extensions.get_extension_for_class(
                    x509.SubjectAlternativeName) else []
                issuer = cert.issuer.rfc4514_string()
                expire_date = cert.not_valid_after.isoformat()
            except Exception as e:
                print(f"Error parsing certificate for {name} in {namespace}: {e}")
                continue

            # Append data
            secrets_data.append({
                "cluster": CLUSTER_NAME,
                "namespace": namespace,
                "secret_name": name,
                "cn": cn,
                "sans": sans,
                "creation_date": creation_date,
                "expire_date": expire_date,
                "issuer": issuer
            })

    return secrets_data


def push_data(data):
    """Send data to the central service."""
    try:
        response = requests.post(API_URL, json=data)
        response.raise_for_status()
        print(f"Data sent successfully: {len(data)} records")
    except requests.RequestException as e:
        print(f"Failed to send data: {e}")

def main():
    secrets_data = get_tls_secrets()
    if secrets_data:
        print(f"Data that would be sent (count: {len(secrets_data)}):")
        print(json.dumps(secrets_data, indent=2))
        # Commented out the actual API call for testing
        # push_data(secrets_data)        time.sleep(CHECK_INTERVAL)


if __name__ == "__main__":
    main()
