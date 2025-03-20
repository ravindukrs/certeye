#!/usr/bin/env python3
import os
import json
import base64
import logging
import signal
import sys
import time
import ipaddress
from typing import Dict, List, Any

import requests
from kubernetes import client, config
from cryptography import x509
from cryptography.hazmat.primitives import serialization
from cryptography.x509.extensions import ExtensionNotFound

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger('certeye-agent')

CLUSTER_NAME = os.getenv("CLUSTER_NAME", "unknown-cluster")
API_URL = os.getenv("API_URL", "http://localhost:5000/ingest")
CHECK_INTERVAL = int(os.getenv("CHECK_INTERVAL", 60))
LOG_LEVEL = os.getenv("LOG_LEVEL", "INFO").upper()
TIMEOUT = int(os.getenv("TIMEOUT", 30))  # Timeout for API calls in seconds
RETRY_INTERVAL = int(os.getenv("RETRY_INTERVAL", 5))  # Seconds between retries
MAX_RETRIES = int(os.getenv("MAX_RETRIES", 3))  # Maximum number of retries

logger.setLevel(getattr(logging, LOG_LEVEL))

is_running = True


def serialize(obj: Any) -> str:
    if isinstance(obj, (ipaddress.IPv4Address, ipaddress.IPv6Address)):
        return str(obj)
    raise TypeError(f"Type {type(obj)} not serializable")


def get_cert_expiration(cert: x509.Certificate) -> str:
    try:
        return cert.not_valid_after_utc.isoformat()
    except AttributeError:
        try:
            return cert.not_valid_after.isoformat()
        except AttributeError:
            return str(getattr(cert, "not_valid_after",
                               getattr(cert, "not_valid_after_utc", "Unknown")))


def get_cert_issue_date(cert: x509.Certificate) -> str:
    return (cert.not_valid_before_utc.isoformat()
            if hasattr(cert, "not_valid_before_utc")
            else cert.not_valid_before.isoformat())


def get_tls_secrets() -> List[Dict[str, Any]]:
    secrets_data = []
    try:
        secrets = core_v1.list_secret_for_all_namespaces().items
    except Exception as e:
        logger.error(f"Failed to list secrets: {e}")
        return []

    secret_count = 0
    error_count = 0

    for secret in secrets:
        if secret.type == "kubernetes.io/tls":
            secret_count += 1
            namespace = secret.metadata.namespace
            name = secret.metadata.name

            cert_data = secret.data.get("tls.crt")
            if not cert_data:
                logger.warning(f"Secret {name} in {namespace} missing tls.crt")
                continue

            try:
                cert_bytes = base64.b64decode(cert_data)
                cert = x509.load_pem_x509_certificate(cert_bytes)

                cn = cert.subject.rfc4514_string()

                sans = []
                try:
                    san_extension = cert.extensions.get_extension_for_class(x509.SubjectAlternativeName)
                    sans = [name.value for name in san_extension.value]
                except ExtensionNotFound:
                    logger.debug(f"No SAN extension found for {name} in {namespace}")

                issuer = cert.issuer.rfc4514_string()
                issue_date = get_cert_issue_date(cert)
                expire_date = get_cert_expiration(cert)

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

                logger.debug(f"Added secret {name} from {namespace}")

            except Exception as e:
                error_count += 1
                logger.error(f"Error parsing certificate for {name} in {namespace}: {e}")
                continue

    logger.info(f"Processed {secret_count} TLS secrets, found {len(secrets_data)}, errors: {error_count}")
    return secrets_data


def push_data(data: List[Dict[str, Any]]) -> bool:
    headers = {
        "Content-Type": "application/json",
        "User-Agent": f"certeye-agent/{CLUSTER_NAME}"
    }

    for attempt in range(MAX_RETRIES):
        try:
            logger.info(f"Sending {len(data)} records to {API_URL}")
            response = requests.post(
                API_URL,
                headers=headers,
                json=data,
                timeout=TIMEOUT
            )

            if response.status_code >= 400:
                logger.warning(f"Server error: {response.status_code} - {response.text}")
                if attempt < MAX_RETRIES - 1:
                    time.sleep(RETRY_INTERVAL)
                    continue
                return False

            logger.info(f"Data sent successfully: {len(data)} records")
            return True

        except requests.RequestException as e:
            logger.error(f"Request failed (attempt {attempt + 1}/{MAX_RETRIES}): {e}")
            if attempt < MAX_RETRIES - 1:
                time.sleep(RETRY_INTERVAL)
            else:
                return False

    return False


def signal_handler(sig, frame):
    global is_running
    logger.info("Received termination signal. Shutting down...")
    is_running = False


def main():
    signal.signal(signal.SIGINT, signal_handler)
    signal.signal(signal.SIGTERM, signal_handler)

    logger.info(f"Certeye agent started. Monitoring cluster: {CLUSTER_NAME}")
    logger.info(f"Checking for certificates every {CHECK_INTERVAL} seconds")

    while is_running:
        try:
            secrets_data = get_tls_secrets()
            if secrets_data:
                push_data(secrets_data)
            else:
                logger.info("No TLS secrets found to send")
        except Exception as e:
            logger.exception(f"Unhandled error in main loop: {e}")

        if is_running:
            logger.debug(f"Sleeping for {CHECK_INTERVAL} seconds")
            for _ in range(min(CHECK_INTERVAL, 60)):
                if not is_running:
                    break
                time.sleep(1)

    logger.info("Agent shutting down")


if __name__ == "__main__":
    try:
        try:
            config.load_incluster_config()
            logger.info("Loaded in-cluster Kubernetes configuration")
        except config.config_exception.ConfigException:
            logger.warning("Unable to load in-cluster config, falling back to kubeconfig")
            config.load_kube_config()

        core_v1 = client.CoreV1Api()
        main()
    except Exception as e:
        logger.exception(f"Fatal error: {e}")
        sys.exit(1)
