#!/usr/bin/env python3
import json
import logging
import os
from flask import Flask, request, jsonify

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
)
logger = logging.getLogger('certeye-service')

PORT = int(os.getenv('PORT', 5000))
DEBUG = os.getenv('DEBUG', 'False').lower() in ('true', '1', 't')
LOG_LEVEL = os.getenv('LOG_LEVEL', 'INFO').upper()

logger.setLevel(getattr(logging, LOG_LEVEL))


def create_app():
    app = Flask(__name__)

    @app.route('/health', methods=['GET'])
    def health_check():
        return jsonify({"status": "healthy"}), 200

    @app.route('/ingest', methods=['POST'])
    def ingest_data():
        if not request.is_json:
            logger.warning("Received non-JSON request")
            return jsonify({"error": "Request must be JSON"}), 415

        try:
            data = request.get_json()

            if not data:
                logger.warning("Empty data received")
                return jsonify({"error": "No data provided"}), 400

            record_count = len(data) if isinstance(data, list) else 1
            logger.info(f"Received {record_count} records from agent")

            if logger.level <= logging.DEBUG:
                # Only log first record in detail if it's a large dataset
                if isinstance(data, list) and len(data) > 1:
                    sample = data[0]
                    logger.debug(f"Sample data: {json.dumps(sample, indent=2)}")
                else:
                    logger.debug(f"Data: {json.dumps(data, indent=2)}")

            return jsonify({
                "status": "success",
                "message": f"Successfully processed {record_count} records"
            }), 200

        except json.JSONDecodeError:
            logger.error("Invalid JSON received")
            return jsonify({"error": "Invalid JSON"}), 400
        except Exception as e:
            logger.exception(f"Error processing request: {e}")
            return jsonify({"error": "Internal server error"}), 500

    return app


if __name__ == "__main__":
    app = create_app()
    logger.info(f"Starting certeye-service on port {PORT}")
    app.run(host="0.0.0.0", port=PORT, debug=DEBUG)
else:
    application = create_app()
