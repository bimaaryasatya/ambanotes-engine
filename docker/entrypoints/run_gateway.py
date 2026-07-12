import os
import sys

BASE_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..'))
sys.path.append(BASE_DIR)

from flask import Flask, jsonify, request, Response
from flask_cors import CORS
import json
import requests
from werkzeug.exceptions import NotFound
from flasgger import Swagger
from graphql_service.schema import schema as graphql_schema

from auth_service.auth_service import auth_bp
from api_gateway.dashboard import dashboard_bp
from common.logger import log_event

app = Flask(__name__)
CORS(app)

swagger_config = {
    "headers": [],
    "specs": [
        {
            "endpoint": "apispec",
            "route": "/apispec.json",
            "rule_filter": lambda rule: True,
            "model_filter": lambda tag: True,
        }
    ],
    "static_url_path": "/flasgger_static",
    "swagger_ui": True,
    "specs_route": "/apidocs/",
    "uiversion": 3,
}

swagger_template = {
    "swagger": "2.0",
    "info": {
        "title": "AmbaNotes REST API",
        "description": "Backend cerdas berbasis AI untuk manajemen dokumen surat",
        "version": "1.0.0",
    },
    "securityDefinitions": {
        "BearerAuth": {
            "type": "apiKey",
            "name": "Authorization",
            "in": "header",
            "description": "Ketik: **Bearer <spasi> token_anda**",
        }
    },
}

Swagger(app, config=swagger_config, template=swagger_template)


@app.route('/graphql', methods=['GET', 'POST'])
def graphql_handler():
    if request.method == 'GET':
        html = """<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="utf-8" />
  <title>AmbaNotes GraphQL</title>
  <link rel="stylesheet" href="https://cdn.jsdelivr.net/npm/graphiql/graphiql.min.css" />
</head>
<body style="margin: 0">
  <div id="graphiql" style="height: 100vh">Loading...</div>
  <script src="https://cdn.jsdelivr.net/npm/react@18.2.0/umd/react.production.min.js"></script>
  <script src="https://cdn.jsdelivr.net/npm/react-dom@18.2.0/umd/react-dom.production.min.js"></script>
  <script src="https://cdn.jsdelivr.net/npm/graphiql@3.4.0/graphiql.min.js"></script>
  <script>
    function graphQLFetcher(url) {
      return async function(graphQLParams) {
        const resp = await fetch(url, {
          method: 'POST',
          headers: {'Content-Type': 'application/json'},
          body: JSON.stringify(graphQLParams),
        });
        return resp.json();
      };
    }
    ReactDOM.render(
      React.createElement(GraphiQL, {fetcher: graphQLFetcher('/graphql')}),
      document.getElementById('graphiql')
    );
  </script>
</body>
</html>"""
        return html
    raw = request.get_data()
    if not raw:
        return jsonify({"error": "Empty request"}), 400
    try:
        data = json.loads(raw.decode("utf-8"))
    except (json.JSONDecodeError, TypeError, UnicodeDecodeError):
        return jsonify({"error": "Invalid JSON"}), 400
    query = data.get("query", "")
    variables = data.get("variables", {})
    result = graphql_schema.execute_sync(query, variable_values=variables)
    resp = {"data": result.data}
    if result.errors:
        resp["errors"] = [{"message": str(e)} for e in result.errors]
    return jsonify(resp)


app.register_blueprint(auth_bp, url_prefix='/auth')
app.register_blueprint(dashboard_bp, url_prefix='')

SERVICE_MAP = {
    'document': 'http://document-pipeline:5001',
    'classification': 'http://document-pipeline:5001',
    'ner': 'http://document-pipeline:5001',
    'ocr': 'http://document-pipeline:5001',
    'ai': 'http://ai-service:5002',
    'generator': 'http://support-services:5003',
    'notification': 'http://support-services:5003',
    'reminder': 'http://support-services:5003',
    'insight': 'http://support-services:5003',
    'verify': 'http://support-services:5003',
}

@app.route('/health', methods=['GET'])
def health_check():
    return jsonify({"status": "healthy", "service": "api_gateway"}), 200

@app.route('/', methods=['GET'])
def index():
    return jsonify({"message": "AmbaNotes API Gateway"}), 200

@app.route('/<path:path>', methods=['GET', 'POST', 'PUT', 'DELETE', 'PATCH'])
def proxy(path):
    if path.startswith('auth/'):
        raise NotFound()
    for prefix, target in SERVICE_MAP.items():
        if path.startswith(prefix) and (len(path) == len(prefix) or path[len(prefix)] == '/'):
            subpath = path[len(prefix):]
            if subpath:
                if not subpath.startswith('/'):
                    subpath = '/' + subpath
                url = f"{target}/{prefix}{subpath}"
            else:
                url = f"{target}/{prefix}"
            if request.query_string:
                url += '?' + request.query_string.decode('utf-8')
            excluded = {'host', 'transfer-encoding', 'connection', 'content-length'}
            headers = {k: v for k, v in request.headers if k.lower() not in excluded}
            headers.pop('Proxy-Authorization', None)
            headers.pop('Proxy-Connection', None)
            body = request.get_data()
            resp = requests.request(
                method=request.method,
                url=url,
                headers=headers,
                data=body,
                timeout=300,
            )
            excluded_resp = {'content-encoding', 'content-length', 'transfer-encoding', 'connection'}
            resp_headers = [(k, v) for k, v in resp.headers.items() if k.lower() not in excluded_resp]
            return Response(resp.content, resp.status_code, resp_headers)
    raise NotFound()

if __name__ == '__main__':
    log_event("api_gateway", "Starting API Gateway (Docker)", action="GATEWAY_START")
    app.run(host='0.0.0.0', port=5009, debug=False)
