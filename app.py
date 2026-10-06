"""CS Document Service - converts and renders documents for the Odoo AI assistant.

Endpoints (all but /health need "Authorization: Bearer <DOCSERVICE_TOKEN>"):
  GET  /health            status, LibreOffice version, number of fonts
  GET  /v1/fonts          font families installed (to check the fonts of Word templates)
  POST /v1/convert/pdf    file=<.docx/.doc/.odt/.xlsx/.pptx>  ->  application/pdf
  POST /v1/render/png     file=<.pdf>, dpi, first, last        ->  {"page_count", "pages": [base64 png]}

Nothing is kept: every request works in its own temporary folder, deleted at the end.
"""
import asyncio
import base64
import hmac
import os
import re
import shutil
import subprocess
import tempfile

from fastapi import Depends, FastAPI, File, Form, Header, HTTPException, UploadFile
from fastapi.responses import Response

TOKEN = os.environ.get('DOCSERVICE_TOKEN', '')
MAX_BYTES = int(os.environ.get('DOCSERVICE_MAX_MB', '30')) * 1024 * 1024
TIMEOUT = int(os.environ.get('DOCSERVICE_TIMEOUT', '180'))
MAX_PAGES = int(os.environ.get('DOCSERVICE_MAX_PAGES', '30'))
SOFFICE = shutil.which('soffice') or shutil.which('libreoffice') or 'soffice'
CONVERTIBLE = ('.docx', '.doc', '.odt', '.rtf', '.xlsx', '.xls', '.ods', '.pptx', '.ppt', '.odp')

# LibreOffice is heavy: a few conversions at a time, the others wait.
SLOTS = asyncio.Semaphore(int(os.environ.get('DOCSERVICE_WORKERS', '2')))

app = FastAPI(title='CS Document Service', version='1.0', docs_url=None, redoc_url=None)


def authorized(authorization: str = Header(default='')):
    if not TOKEN:
        raise HTTPException(503, 'DOCSERVICE_TOKEN is not set on the server.')
    sent = authorization[7:] if authorization.lower().startswith('bearer ') else ''
    if not hmac.compare_digest(sent.encode(), TOKEN.encode()):
        raise HTTPException(401, 'Invalid token.')


async def _read(upload: UploadFile, extensions):
    name = os.path.basename(upload.filename or 'file')
    if not name.lower().endswith(extensions):
        raise HTTPException(415, 'Unsupported file type: %s' % name)
    data = await upload.read(MAX_BYTES + 1)
    if len(data) > MAX_BYTES:
        raise HTTPException(413, 'File larger than %s MB.' % (MAX_BYTES // 1024 // 1024))
    if not data:
        raise HTTPException(400, 'Empty file.')
    return name, data


def _run(cmd):
    try:
        return subprocess.run(cmd, check=True, timeout=TIMEOUT, capture_output=True)
    except subprocess.TimeoutExpired as e:
        raise HTTPException(504, 'Processing took more than %s seconds.' % TIMEOUT) from e
    except subprocess.CalledProcessError as e:
        raise HTTPException(422, 'Processing failed: %s' % (e.stderr or b'').decode(errors='replace')[-500:]) from e


def _convert(name, data):
    with tempfile.TemporaryDirectory() as tmp:
        source = os.path.join(tmp, 'document' + os.path.splitext(name)[1].lower())
        with open(source, 'wb') as f:
            f.write(data)
        # One LibreOffice profile per request: parallel conversions do not lock each other.
        _run([SOFFICE, '--headless', '--norestore', '-env:UserInstallation=file://%s/profile' % tmp,
              '--convert-to', 'pdf', '--outdir', tmp, source])
        target = os.path.join(tmp, 'document.pdf')
        if not os.path.exists(target):
            raise HTTPException(422, 'LibreOffice produced no PDF.')
        with open(target, 'rb') as f:
            return f.read()


def _page_count(path):
    out = _run(['pdfinfo', path]).stdout.decode(errors='replace')
    match = re.search(r'^Pages:\s+(\d+)', out, re.M)
    return int(match.group(1)) if match else 0


def _render(data, dpi, first, last):
    with tempfile.TemporaryDirectory() as tmp:
        source = os.path.join(tmp, 'document.pdf')
        with open(source, 'wb') as f:
            f.write(data)
        count = _page_count(source)
        first = max(1, first)
        last = min(count, last or count, first + MAX_PAGES - 1)
        if count and first <= last:
            _run(['pdftoppm', '-png', '-r', str(dpi), '-f', str(first), '-l', str(last), source,
                  os.path.join(tmp, 'page')])
        pages = []
        for name in sorted(n for n in os.listdir(tmp) if n.startswith('page') and n.endswith('.png')):
            with open(os.path.join(tmp, name), 'rb') as f:
                pages.append(base64.b64encode(f.read()).decode())
        return {'page_count': count, 'first': first, 'pages': pages}


@app.get('/health')
def health():
    try:
        version = subprocess.run([SOFFICE, '--version'], capture_output=True, timeout=30).stdout.decode().strip()
    except (OSError, subprocess.SubprocessError):
        version = ''
    return {'status': 'ok' if version else 'degraded', 'libreoffice': version, 'fonts': len(_fonts())}


def _fonts():
    try:
        out = subprocess.run(['fc-list', ':', 'family'], capture_output=True, timeout=30).stdout.decode()
    except (OSError, subprocess.SubprocessError):
        return []
    return sorted({f.strip() for line in out.splitlines() for f in line.split(',') if f.strip()})


@app.get('/v1/fonts', dependencies=[Depends(authorized)])
def fonts():
    return {'fonts': _fonts()}


@app.post('/v1/convert/pdf', dependencies=[Depends(authorized)])
async def convert_pdf(file: UploadFile = File(...)):
    name, data = await _read(file, CONVERTIBLE)
    async with SLOTS:
        pdf = await asyncio.to_thread(_convert, name, data)
    return Response(pdf, media_type='application/pdf')


@app.post('/v1/render/png', dependencies=[Depends(authorized)])
async def render_png(file: UploadFile = File(...), dpi: int = Form(110), first: int = Form(1),
                     last: int = Form(0)):
    _name, data = await _read(file, ('.pdf',))
    dpi = min(max(dpi, 50), 200)
    async with SLOTS:
        return await asyncio.to_thread(_render, data, dpi, first, last)
