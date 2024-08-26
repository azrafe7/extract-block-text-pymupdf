from fastapi import FastAPI, HTTPException, Query, Body
from fastapi.responses import JSONResponse, Response, FileResponse
from pydantic import BaseModel, HttpUrl
import requests
from io import BytesIO
# from pypdf import PdfReader, PdfWriter, generic, ObjectDeletionFlag
# import pypdfium2 as pdfium
import fitz  # PyMuPDF
from extract_text_info import highlight_sentences_in_pdf
from PIL import Image
import os
import logging
from typing import Optional, cast

logger = logging.getLogger('uvicorn.error')
logger.setLevel(logging.DEBUG)

app = FastAPI()


OUTPUT_MEDIA_TYPES = {
    0: 'application/pdf',
    1: 'image/png',
    2: 'image/jpeg',
}

DEFAULT_X_TOLERANCE = None
DEFAULT_Y_TOLERANCE = None

HIGHLIGHTED_SUFFIX = '_highlighted'


class ProcessRequest(BaseModel):
    file_url: HttpUrl
    use_clustered_blocks: Optional[bool] = False
    x_tolerance: Optional[int] = DEFAULT_X_TOLERANCE
    y_tolerance: Optional[int] = DEFAULT_Y_TOLERANCE


@app.get("/")
async def root():
    return {"message": "Server running"}

@app.get("/test")
async def test_page():
    return FileResponse('test.html')

def process_pdf(file_url: str, use_clustered_blocks: Optional[bool] = False, x_tolerance: Optional[int] = DEFAULT_X_TOLERANCE, y_tolerance: Optional[int] = DEFAULT_Y_TOLERANCE):
    logger.debug(f"Processing '{file_url}'")
    logger.debug(f"Use clustered blocks: {use_clustered_blocks}")
    if use_clustered_blocks:
        logger.debug(f"  x_tolerance: {x_tolerance}")
        logger.debug(f"  y_tolerance: {y_tolerance}")
    
    # Check if the input file has a .pdf extension
    file_url = str(file_url) # force-convert to str
    if not file_url.lower().endswith('.pdf'):
        raise HTTPException(status_code=400, detail="Input file must have a .pdf extension")

    # Fetch the PDF file from the URL
    response = requests.get(file_url)
    response.raise_for_status()
    pdf_content = response.content

    # Create a Pdf Document object from the fetched content
    pdf_document = fitz.Document(stream=BytesIO(pdf_content))
    
    json_data, result_pdf_document = highlight_sentences_in_pdf(pdf_document)

    # Generate the output filename
    input_filename = os.path.basename(file_url)
    # output_filename = os.path.splitext(input_filename)[0] + '_processed.pdf'

    return result_pdf_document, json_data, input_filename

@app.post("/extract_text")
async def extract_text_post(request: ProcessRequest):
    if not request:
        raise HTTPException(status_code=400, detail="Missing JSON payload. Please provide 'file_url' in the request body.")
    return process_request(request.file_url, request.use_clustered_blocks, request.x_tolerance, request.y_tolerance)

@app.get("/extract_text")
async def extract_text_get(file_url: str, use_clustered_blocks: Optional[bool] = False, x_tolerance: Optional[int] = DEFAULT_X_TOLERANCE, y_tolerance: Optional[int] = DEFAULT_Y_TOLERANCE):
    if file_url is None:
        raise HTTPException(status_code=400, detail="Missing 'file_url' parameter in the query string.")
    return process_request(file_url, use_clustered_blocks, x_tolerance, y_tolerance)

def process_request(file_url: str, use_clustered_blocks: Optional[bool] = False, x_tolerance: Optional[int] = DEFAULT_X_TOLERANCE, y_tolerance: Optional[int] = DEFAULT_Y_TOLERANCE):
    try:
        output_pdf, output_json, input_filename = process_pdf(file_url, use_clustered_blocks=use_clustered_blocks, x_tolerance=x_tolerance, y_tolerance=y_tolerance)

        # Return the PDF as a downloadable file along with the response message
        media_type = OUTPUT_MEDIA_TYPES[0]
        # breakpoint()
        output_filename = os.path.splitext(input_filename)[0] + f"{HIGHLIGHTED_SUFFIX}.pdf"
        headers = {
            # "Content-Disposition": f"attachment; filename={output_filename}",
            "Content-Type": media_type,
        }

        # Prepare the response message
        response_data = Response(
            content=output_pdf.write(),
            media_type=media_type,
            headers=headers,
        )

        return response_data

    except HTTPException as he:
        raise he
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=5000)