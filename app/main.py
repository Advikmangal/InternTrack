from pathlib import Path
import logging
from fastapi import FastAPI, Request, HTTPException
from fastapi.exceptions import RequestValidationError
from fastapi.responses import FileResponse, JSONResponse, HTMLResponse
from fastapi.staticfiles import StaticFiles
from starlette.exceptions import HTTPException as StarletteHTTPException
from .config import settings
from .routers import authentication, applications, planning, dashboard, resumes

app = FastAPI(title='InternTrack API', version='1.0.0', docs_url=None, redoc_url=None)
static = Path(__file__).parent / 'static'


def error_response(request, status, message=None, headers=None):
    # API clients always receive JSON, including when opened in a browser.
    if request.url.path.startswith('/api/') or request.url.path == '/api' or 'text/html' not in request.headers.get('accept', ''):
        return JSONResponse({'error': message or 'Something went wrong. Please try again.'}, status_code=status, headers=headers)
    pages = {
        404: ('PAGE NOT FOUND', 'A wrong turn. Not a dead end.', 'This page does not exist, or the link is no longer available.', 'Check the address, or return to your workspace.'),
        403: ('ACCESS RESTRICTED', 'This page is out of reach.', 'You do not have permission to open this page.', 'Return to your workspace to continue.'),
        401: ('SIGN-IN REQUIRED', 'Let’s get you back in.', 'Please log in to access your private workspace.', 'Your saved work will be waiting for you.'),
    }
    label, title, description, hint = pages.get(status, ('REQUEST INTERRUPTED', 'A pause in the process.', 'We could not load this page. Please try again shortly.', 'If the problem continues, return later.'))
    html = (static / 'error.html').read_text(encoding='utf-8')
    for key, value in {'code': str(status), 'label': label, 'title': title, 'message': description, 'hint': hint}.items():
        html = html.replace('{{' + key + '}}', value)
    return HTMLResponse(html, status_code=status, headers=headers)


@app.middleware('http')
async def security(request: Request, call_next):
    if request.method not in ('GET', 'HEAD', 'OPTIONS'):
        # Origin validation also protects login/register before a session exists.
        origin = request.headers.get('origin')
        if origin not in settings.allowed_origins:
            return JSONResponse({'error': 'Request origin is not allowed'}, status_code=403)
        length = request.headers.get('content-length')
        if length and (not length.isdigit() or int(length) > (settings.max_upload_mb + 1) * 1024 * 1024):
            return JSONResponse({'error': 'Request is too large'}, status_code=413)
    try:
        response = await call_next(request)
    except Exception:
        logging.getLogger(__name__).exception('Unhandled request error')
        response = error_response(request, 500, 'The server could not complete the request. Please try again shortly.')
    response.headers['X-Content-Type-Options'] = 'nosniff'
    response.headers['Referrer-Policy'] = 'same-origin'
    response.headers['X-Frame-Options'] = 'DENY'
    response.headers['Content-Security-Policy'] = "default-src 'self'; script-src 'self'; style-src 'self'; img-src 'self' data:; connect-src 'self'; frame-ancestors 'none'; object-src 'none'; base-uri 'self'; form-action 'self'"
    if request.url.path == '/docs':
        # Swagger UI uses inline layout styles; application pages keep the stricter policy.
        response.headers['Content-Security-Policy'] = response.headers['Content-Security-Policy'].replace("style-src 'self'", "style-src 'self' 'unsafe-inline'")
    if request.url.path.startswith('/api'):
        response.headers['Cache-Control'] = 'no-store'
    return response


@app.exception_handler(StarletteHTTPException)
async def http_error(request, exc):
    return error_response(request, exc.status_code, exc.detail, exc.headers)


@app.exception_handler(RequestValidationError)
async def validation_error(request, exc):
    details = [{'field': '.'.join(map(str, e['loc'][1:])), 'message': e['msg']} for e in exc.errors()]
    return JSONResponse({'error': 'Please check the highlighted values', 'details': details}, status_code=422)


for router in (authentication.router, applications.router, planning.router, dashboard.router, resumes.router):
    app.include_router(router)
app.mount('/static', StaticFiles(directory=static), name='static')


@app.get('/', include_in_schema=False)
def index():
    return FileResponse(static / 'index.html')


@app.get('/docs', include_in_schema=False)
def docs():
    return FileResponse(static / 'docs.html')


@app.get('/health', tags=['Health'])
def health():
    return {'status': 'ok'}
