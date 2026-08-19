#!/bin/bash

export GOOGLE_CLIENT_ID="$(python3 -c 'import json; print(json.load(open("client_secret_919803026892-digob6irqi5nmajt3pl5ggk7hmp84msn.apps.googleusercontent.com.json"))["web"]["client_id"])')"

export GOOGLE_CLIENT_SECRET="$(python3 -c 'import json; print(json.load(open("client_secret_919803026892-digob6irqi5nmajt3pl5ggk7hmp84msn.apps.googleusercontent.com.json"))["web"]["client_secret"])')"

export MCP_TRANSPORT=http
export PORT=3005

npx -y google-drive-mcp@1.3.0
