#!/bin/sh
# Index the fonts (those of the image and those mounted from the host), then start the service.
set -e
fc-cache -f >/dev/null 2>&1 || true
exec uvicorn app:app --host 0.0.0.0 --port 8000 --workers 1
