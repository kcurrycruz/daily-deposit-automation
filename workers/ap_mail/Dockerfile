FROM mcr.microsoft.com/playwright:v1.62.1-noble@sha256:dcc5531e97840b9b5e794f2814476b21571c5124a3fca2267d73041f56e7580e
USER root
RUN apt-get update && apt-get install -y --no-install-recommends python3 python3-venv && rm -rf /var/lib/apt/lists/*
WORKDIR /opt/ap-mail
COPY workers/ap_mail/requirements.lock workers/ap_mail/requirements.lock
RUN python3 -m venv /opt/venv && /opt/venv/bin/pip install --no-cache-dir --require-hashes -r workers/ap_mail/requirements.lock
COPY app/ap_statements/package*.json app/ap_statements/
COPY workers/ap_mail/package*.json workers/ap_mail/
RUN npm ci --prefix app/ap_statements --ignore-scripts --no-audit --no-fund && PLAYWRIGHT_SKIP_BROWSER_DOWNLOAD=1 npm ci --prefix workers/ap_mail --ignore-scripts --no-audit --no-fund
COPY app/ap_mail app/ap_mail
COPY app/ap_shared app/ap_shared
COPY app/ap_statements/frontend app/ap_statements/frontend
COPY app/ap_statements/build.mjs app/ap_statements/build.mjs
COPY app/ap_statements/streamlit_bridge.mjs app/ap_statements/streamlit_bridge.mjs
COPY app/ap_statements/bridge_core.mjs app/ap_statements/bridge_core.mjs
COPY app/ap_statements/licenses app/ap_statements/licenses
COPY workers/ap_mail workers/ap_mail
RUN node app/ap_statements/build.mjs && node -e "if(process.versions.node.split('.')[0]!=='24')process.exit(1)" && python3 -c "import sys;assert sys.version_info[:2]==(3,12)"
ENV PATH="/opt/venv/bin:$PATH" PYTHONPATH="/opt/ap-mail" PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1
USER pwuser
EXPOSE 8080
CMD ["gunicorn", "--bind", "0.0.0.0:8080", "--workers", "1", "--threads", "1", "--timeout", "610", "--graceful-timeout", "30", "workers.ap_mail.http:create_app()"]
