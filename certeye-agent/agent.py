import os
import json
import base64
import requests
import ipaddress
import time
from kubernetes import client, config
from cryptography import x509
from cryptography.hazmat.primitives import serialization
from cryptography.x509.extensions import ExtensionNotFound

# Load environment variables
CLUSTER_NAME = os.getenv("CLUSTER_NAME", "unknown-cluster")
API_URL = os.getenv("API_URL", "http://localhost:5000/ingest")
CHECK_INTERVAL = int(os.getenv("CHECK_INTERVAL", 60))

# Load Kubernetes configuration
config.load_incluster_config()
core_v1 = client.CoreV1Api()

def serialize(obj):
    """Ensure JSON serialization of non-serializable objects."""
    if isinstance(obj, (ipaddress.IPv4Address, ipaddress.IPv6Address)):
        return str(obj)
    raise TypeError(f"Type {type(obj)} not serializable")

def get_tls_secrets():
    """Fetch TLS secrets from all namespaces."""
    secrets_data = []
    secrets = core_v1.list_secret_for_all_namespaces().items

    for secret in secrets:
        if secret.type == "kubernetes.io/tls":
            namespace = secret.metadata.namespace
            name = secret.metadata.name
            cert_data = secret.data.get("tls.crt")
            if not cert_data:
                continue

            try:
                cert_bytes = base64.b64decode(cert_data)
                cert = x509.load_pem_x509_certificate(cert_bytes)

                cn = cert.subject.rfc4514_string()
                try:
                    san_extension = cert.extensions.get_extension_for_class(x509.SubjectAlternativeName)
                    sans = [name.value for name in san_extension.value]
                except ExtensionNotFound:
                    sans = []
                
                issuer = cert.issuer.rfc4514_string()
                issue_date = cert.not_valid_before_utc.isoformat() if hasattr(cert,
                                                                              "not_valid_before_utc") else cert.not_valid_before.isoformat()
                try:
                    expire_date = cert.not_valid_after_utc.isoformat()
                except AttributeError:
                    try:
                        expire_date = cert.not_valid_after.isoformat()
                    except AttributeError:
                        expire_date = str(getattr(cert, "not_valid_after",
                                                  getattr(cert, "not_valid_after_utc", "Unknown")))
            except Exception as e:
                print(f"Error parsing certificate for {name} in {namespace}: {e}")
                continue

            secrets_data.append({
                "cluster": CLUSTER_NAME,
                "namespace": namespace,
                "secret_name": name,
                "cn": cn,
                "sans": sans,
                "issue_date": issue_date,
                "expire_date": expire_date,
                "issuer": issuer
            })

            print(f"Added secret {name} from {namespace}: {secrets_data[-1]}")


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
    while True:
        secrets_data = get_tls_secrets()
        if secrets_data:
            print(f"Data that would be sent (count: {len(secrets_data)}):")
            print(json.dumps(secrets_data, indent=2, default=serialize))
        time.sleep(CHECK_INTERVAL)

if __name__ == "__main__":
    main()
