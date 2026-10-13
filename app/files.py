from io import BytesIO
from fastapi import HTTPException
from pypdf import PdfReader


def validate_pdf(filename, content):
    if not filename or not filename.lower().endswith('.pdf') or not content.startswith(b'%PDF-'):
        raise HTTPException(422, 'Upload a valid PDF file with a .pdf extension')
    try:
        reader = PdfReader(BytesIO(content), strict=True)
        if reader.is_encrypted or not len(reader.pages):
            raise ValueError('Empty or encrypted PDF')
        # Reject active content. PDFs are served as downloads, never public/inline.
        visited = set()
        def inspect(obj, depth=0):
            if depth > 80:
                raise ValueError('PDF structure is too complex')
            if hasattr(obj, 'get_object'):
                obj = obj.get_object()
            marker = id(obj)
            if marker in visited:
                return
            visited.add(marker)
            if isinstance(obj, dict):
                if any(k in obj for k in ('/JS', '/JavaScript', '/Launch', '/EmbeddedFiles', '/OpenAction', '/AA')):
                    raise ValueError('Active PDF content is not allowed')
                for value in obj.values():
                    inspect(value, depth + 1)
            elif isinstance(obj, list):
                for value in obj:
                    inspect(value, depth + 1)
        inspect(reader.trailer)
    except Exception:
        raise HTTPException(422, 'PDF is corrupt, encrypted, empty, or contains active content')
