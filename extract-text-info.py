import fitz  # PyMuPDF
import argparse
import os
import re
import json
import PIL


HIGHLIGHTED_SUFFIX = '_highlighted'


def get_texts_in_block(block, as_spans=False):
    texts = []
    for line in block['lines']:
        texts.append([span if as_spans else span['text'] for span in line['spans']])
    return texts

def get_texts_in_lines(lines, as_spans=False):
    texts = []
    for line in lines:
        texts.append([span if as_spans else span['text'] for span in line['spans']])
    return texts

def highlight_sentences_in_pdf(input_pdf_path, output_pdf_path):

    # Open the PDF file
    pdf_document = fitz.open(input_pdf_path)

    # Regular expression to split text into sentences
    sentence_endings = re.compile(r'(?<!\w\.\w.)(?<![A-Z][a-z]\.)(?<=\.|\?)\s')

    pdf_data = []
    
    # Iterate through each page in the PDF
    for page_number in range(min(8, pdf_document.page_count)):
        page = pdf_document[page_number]
        
        text_models = []
        image_models = []
        block_models = []
        page_data = { 
            "pageNumber": str(page_number + 1),
            "pageWidth": str(page.rect[2] - page.rect[0]),
            "pageHight": str(page.rect[3] - page.rect[1]),
            "textsModelsList": text_models,
            "blocks": block_models,
            "imagesModelsList": image_models,
        }

        # breakpoint()
        # ocred_page = page.get_textpage_ocr()

        # Drawings
        #drawings = page.get_drawings()
        #drawings = page.cluster_drawings(drawings=drawings, x_tolerance=5, y_tolerance=3)
        #for rect_index, rect in enumerate(drawings):
        ## for rect_index, drawing in enumerate(drawings[:]):
        #    # rect = drawing["rect"]
        #    try:
        #        highlight = page.add_rect_annot(rect)
        #    except ValueError as e:
        #        print(f"{e}")
        #        pass;
        #    highlight.set_colors(stroke=[1, .8, 0])  # Orange rectangle
        #    highlight.update()
        #    if rect_index == 0 or (rect_index + 1) % 10 == 0:
        #        print(f"drawing rect {rect_index + 1}/{len(drawings)}")
        #    # page.add_redact_annot(rect)
        ## page.apply_redactions(0,2,1)  # potentially set options for any of images, drawings, text

        # Draw rectangles around each image
        for image_index, image_info in enumerate(page.get_image_info(xrefs=True)):
            # breakpoint()
            bbox = list(image_info['bbox'])

            image_model = {
                "imageXPos": str(bbox[0]),
                "imageYPos": str(bbox[1]),
                "imageWidth": str(image_info['width']),
                "imageHeight": str(image_info['height']),
            }
            image_models.append(image_model)
            
            # Save image
            #if image_info['xref']:
            #    image_data = pdf_document.extract_image(image_info['xref'])
            #    imgout = open(f"image{page_number}-{image_index}.{image_data['ext']}", "wb")
            #    imgout.write(image_data["image"])
            #    imgout.close()
        
            # for k in range(len(bbox)): bbox[k] += 2 if k < 2 else -2  # shrink bbox
            highlight = page.add_rect_annot(bbox)
            highlight.set_colors(stroke=[0, .2, 1])  # Blue rectangle
            highlight.update()

        # Extract text with formatting information
        blocks = page.get_text("dict")["blocks"]
        
        for block_index, block in enumerate(blocks):
            if block['type'] == 0:  # Text block
                lines = block['lines']
                block_texts = []
                
                # Draw rectangles around each line
                for line_index, line in enumerate(lines):
                    spans = [span for span in line['spans'] if span['text']]
                    text = ''.join([span['text'] for span in spans])
                    print(f"[page {page_number}] spans text in block {block_index} line {line_index}: '{text}'")
                    bbox = line['bbox']
                    highlight = page.add_rect_annot(bbox)
                    highlight.set_colors(stroke=[1, 0, 0])  # Red rectangle
                    highlight.update()
                    # Add annotation with line text
                    text_annot = page.add_text_annot((bbox[2]-2, bbox[3]-2), text, icon="Comment")
                    text_annot.set_colors(stroke=[1, 0, 0])  # Red
                    text_annot.update(opacity=.7)
                    
                    for span in spans:
                        # breakpoint()
                        text_model = {
                            "parentBlockNumber": str(block_index),
                            "textBoxName": str(span['text']),
                            "textXPos": str(span['bbox'][0]),
                            "textYPos": str(span['bbox'][1]),
                            "textBoundingBox": ",".join([str(value) for value in span['bbox']]),
                            "fontSize": span['size'],
                            "fontFamily": span['font']
                        }
                        text_models.append(text_model)
                    
                    block_texts.append(text)
                
                block_text = "\n".join(block_texts)

                block_model = {
                    "number": str(block_index),
                    "text": block_text,
                    "boundingBox": ",".join([str(value) for value in block['bbox']])
                }
                block_models.append(block_model)
                
                # Draw rectangles around each block
                # breakpoint()
                bbox = list(block['bbox'])
                for k in range(len(bbox)): bbox[k] += -1 if k < 2 else +1  # expand bbox
                highlight = page.add_rect_annot(bbox)
                highlight.set_colors(stroke=[0, .8, 0])  # Green rectangle
                highlight.update()
                # Add annotation with block text
                text_annot = page.add_text_annot((bbox[0]-18, bbox[1]-18), block_text, icon="Paragraph")
                text_annot.set_colors(stroke=[0, 1, 0])  # Green
                text_annot.update(opacity=.7)
        
        pdf_data.append(page_data)
        
        
    # Save the modified PDF to a new file
    pdf_document.save(output_pdf_path)
    pdf_document.close()
    return pdf_data

def main():
    # Parse command-line arguments
    parser = argparse.ArgumentParser(description='Highlight sentences in a PDF file.')
    parser.add_argument('input_pdf', help='Path to the input PDF file.')
    parser.add_argument('--output_pdf', help=f'Path to the output PDF file. Defaults to "<input_pdf>{HIGHLIGHTED_SUFFIX}.pdf".')

    args = parser.parse_args()

    # Determine the output file name
    input_pdf = args.input_pdf
    output_pdf = args.output_pdf or os.path.splitext(input_pdf)[0] + f"{HIGHLIGHTED_SUFFIX}.pdf"
    output_json = os.path.splitext(output_pdf)[0] + ".json"

    # Highlight the sentences in the PDF
    json_data = highlight_sentences_in_pdf(input_pdf, output_pdf)
    print()
    print(f"Highlighted PDF saved as: {output_pdf}")
    
    with open(output_json, 'w', encoding='utf-8') as f:
        json.dump(json_data, f, indent=2)
        print(f"JSON data saved as: {output_json}")

if __name__ == "__main__":
    main()
