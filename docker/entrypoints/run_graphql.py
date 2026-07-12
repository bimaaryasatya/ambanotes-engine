import os
import sys
import json

BASE_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..'))
sys.path.append(BASE_DIR)

from flask import Flask, jsonify, request
from flask_cors import CORS
from graphql_service.schema import schema

app = Flask(__name__)
CORS(app)


@app.route('/graphql', methods=['GET', 'POST'])
def graphql():
    if request.method == 'GET':
        html = """<!DOCTYPE html>
<html>
<head>
  <title>AmbaNotes GraphQL</title>
</head>
<body style="margin:0;height:100vh">
  <div id="graphiql">Loading...</div>
  <link rel="stylesheet" href="https://unpkg.com/graphiql@latest/graphiql.min.css" />
  <script crossorigin src="https://unpkg.com/react@18/umd/react.production.min.js"></script>
  <script crossorigin src="https://unpkg.com/react-dom@18/umd/react-dom.production.min.js"></script>
  <script crossorigin src="https://unpkg.com/graphiql@latest/graphiql.min.js"></script>
  <script>
    const fetcher = GraphiQL.createFetcher({url: '/graphql'});
    ReactDOM.render(React.createElement(GraphiQL, {fetcher}), document.getElementById('graphiql'));
  </script>
</body>
</html>"""
        return html

    data = request.get_json(silent=True)
    if not data:
        return jsonify({"error": "Invalid request"}), 400

    query = data.get("query", "")
    variables = data.get("variables", {})
    result = schema.execute_sync(query, variable_values=variables)

    resp = {"data": result.data}
    if result.errors:
        resp["errors"] = [{"message": str(e)} for e in result.errors]
    return jsonify(resp)


@app.route('/health', methods=['GET'])
def health_check():
    return jsonify({"status": "healthy", "service": "graphql_service"}), 200


if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5004, debug=True)
