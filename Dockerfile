FROM python:3.12-slim-bookworm

# LibreOffice (Word -> PDF), poppler (PDF -> images), fonts (Arabic + Latin)
RUN apt-get update \
 && apt-get install -y --no-install-recommends \
      libreoffice-writer-nogui libreoffice-calc-nogui libreoffice-impress-nogui \
      poppler-utils fontconfig \
      fonts-noto-core fonts-noto-ui-core fonts-kacst fonts-hosny-amiri fonts-dejavu fonts-liberation2 \
      fonts-crosextra-carlito fonts-crosextra-caladea \
 && rm -rf /var/lib/apt/lists/*

# The fonts of your Word templates (Hacen Tunisia, Cairo...): put the .ttf/.otf files in fonts/
COPY fonts/ /usr/local/share/fonts/custom/
RUN fc-cache -f

WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY app.py entrypoint.sh ./
# Windows line endings would break the script on Linux
RUN sed -i 's/\r$//' entrypoint.sh && chmod +x entrypoint.sh \
 && mkdir -p /usr/local/share/fonts/host

RUN useradd --create-home docservice
USER docservice
ENV HOME=/home/docservice
EXPOSE 8000
HEALTHCHECK --interval=60s --timeout=30s CMD python -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8000/health')"
CMD ["./entrypoint.sh"]
