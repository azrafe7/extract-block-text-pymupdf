from fastapi import FastAPI, HTTPException, Query, Body
from fastapi.responses import JSONResponse, Response, FileResponse
from pydantic import BaseModel, HttpUrl
import requests
from io import BytesIO
# from pypdf import PdfReader, PdfWriter, generic, ObjectDeletionFlag
# import pypdfium2 as pdfium
import fitz  # PyMuPDF
import extract_text_info
from extract_text_info import highlight_sentences_in_pdf
from PIL import Image
import os
import logging
from typing import Optional, cast
import json

logger = logging.getLogger('uvicorn.error')
logger.setLevel(logging.DEBUG)

app = FastAPI()


OUTPUT_MEDIA_TYPES = {
    0: 'application/json',
    1: 'application/pdf',
    2: 'text/html',
}

DEFAULT_OUTPUT_TYPE = 0

HIGHLIGHTED_SUFFIX = extract_text_info.HIGHLIGHTED_SUFFIX

# clustered blocks params
DEFAULT_USE_CLUSTERED_BLOCKS = extract_text_info.DEFAULT_USE_CLUSTERED_BLOCKS
DEFAULT_USE_CLUSTERED_SPANS = extract_text_info.DEFAULT_USE_CLUSTERED_SPANS
DEFAULT_X_TOLERANCE = extract_text_info.DEFAULT_X_TOLERANCE
DEFAULT_Y_TOLERANCE = extract_text_info.DEFAULT_Y_TOLERANCE


class ProcessRequest(BaseModel):
    file_url: HttpUrl
    use_clustered_blocks: Optional[bool] = False
    use_clustered_spans: Optional[bool] = False
    x_tolerance: Optional[int] = DEFAULT_X_TOLERANCE
    y_tolerance: Optional[int] = DEFAULT_Y_TOLERANCE
    output_type: Optional[int] = DEFAULT_OUTPUT_TYPE


@app.get("/")
async def root():
    return {"message": "Server running"}

@app.get("/test")
async def test_page():
    return FileResponse('test.html')

def process_pdf(file_url: str, use_clustered_blocks: Optional[bool] = DEFAULT_USE_CLUSTERED_BLOCKS, use_clustered_spans: Optional[bool] = DEFAULT_USE_CLUSTERED_SPANS, x_tolerance: Optional[int] = DEFAULT_X_TOLERANCE, y_tolerance: Optional[int] = DEFAULT_Y_TOLERANCE, output_type: Optional[int] = DEFAULT_OUTPUT_TYPE):
    logger.debug(f"Processing '{file_url}'")
    logger.debug(f"Use clustered blocks: {use_clustered_blocks}")
    logger.debug(f"Use clustered spans: {use_clustered_spans}")
    if use_clustered_blocks or use_clustered_spans:
        logger.debug(f"  x_tolerance: {x_tolerance}")
        logger.debug(f"  y_tolerance: {y_tolerance}")
    logger.debug(f"Output type: '{OUTPUT_MEDIA_TYPES[output_type]}'")
    
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
    
    json_data, result_pdf_document = highlight_sentences_in_pdf(pdf_document, use_clustered_blocks=use_clustered_blocks, use_clustered_spans=use_clustered_spans, x_tolerance=x_tolerance, y_tolerance=y_tolerance)

    # Generate the output filename
    input_filename = os.path.basename(file_url)
    # output_filename = os.path.splitext(input_filename)[0] + '_processed.pdf'

    return result_pdf_document, json_data, input_filename

@app.post("/extract_text")
async def extract_text_post(request: ProcessRequest):
    if not request:
        raise HTTPException(status_code=400, detail="Missing JSON payload. Please provide 'file_url' in the request body.")
    return process_request(request.file_url, request.use_clustered_blocks, request.use_clustered_spans, request.x_tolerance, request.y_tolerance, request.output_type)

@app.get("/extract_text")
async def extract_text_get(file_url: str, use_clustered_blocks: Optional[bool] = DEFAULT_USE_CLUSTERED_BLOCKS, use_clustered_spans: Optional[bool] = DEFAULT_USE_CLUSTERED_SPANS, x_tolerance: Optional[int] = DEFAULT_X_TOLERANCE, y_tolerance: Optional[int] = DEFAULT_Y_TOLERANCE, output_type: Optional[int] = DEFAULT_OUTPUT_TYPE):
    if file_url is None:
        raise HTTPException(status_code=400, detail="Missing 'file_url' parameter in the query string.")
    return process_request(file_url=file_url, use_clustered_blocks=use_clustered_blocks, use_clustered_spans=use_clustered_spans, x_tolerance=x_tolerance, y_tolerance=y_tolerance, output_type=output_type)

def process_request(file_url: str, use_clustered_blocks: Optional[bool] = DEFAULT_USE_CLUSTERED_BLOCKS, use_clustered_spans: Optional[bool] = DEFAULT_USE_CLUSTERED_SPANS, x_tolerance: Optional[int] = DEFAULT_X_TOLERANCE, y_tolerance: Optional[int] = DEFAULT_Y_TOLERANCE, output_type: Optional[int] = DEFAULT_OUTPUT_TYPE):
    try:
        output_pdf, output_data, input_filename = process_pdf(file_url, use_clustered_blocks=use_clustered_blocks, use_clustered_spans=use_clustered_spans, x_tolerance=x_tolerance, y_tolerance=y_tolerance, output_type=output_type)

        if output_type == 0:
            output_data = json.dumps(
                output_data, 
                # indent=2
            )
        elif output_type == 2:  # text only
            page_blocks = []
            for page_idx, page in enumerate(output_data):
                text_blocks = []
                page_number = page["page_number"]
                page_block = {"page": page_number, "texts": text_blocks}
                for block in page["blocks"]:
                    text_blocks.append(block["text"])
                page_blocks.append(page_block)
            
            output_data = '''
<html>
  <head>
    <meta charset="UTF-8">
    <style>
    body {
      font-family: monospace;
    }
    .page {
      margin-top: 1em; 
      font-size: 1.2em;
      font-weight: bold;
    }
    .text-caption {
      margin-left: 1em; 
      margin-top: .75em;
      font-weight: bold;
    }
    .text {
      margin-left: 1em;
      margin-top:.2em; 
      border:1px solid #1d1;
    }
    </style>
  </head>'''
            for page_block in page_blocks:
                output_data += f'<div class="page">Page {page_block["page"]}</div>'
                for text_idx, text in enumerate(page_block["texts"]):
                    output_data += f'<div class="text-caption">#{text_idx + 1}</div>'
                    output_data += f'<div class="text">{text}</div>'
            output_data += f'</html>'

        
        # Return the PDF as a downloadable file along with the response message
        media_type = OUTPUT_MEDIA_TYPES[output_type]
        # output_filename = os.path.splitext(input_filename)[0] + f"{HIGHLIGHTED_SUFFIX}.pdf"
        headers = {
            # "Content-Disposition": f"attachment; filename={output_filename}",
            "Content-Type": media_type,
        }

        # Prepare the response message
        # breakpoint()
        response_data = Response(
            content=output_pdf.write() if 'pdf' in media_type else output_data,
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