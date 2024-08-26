import fitz  # PyMuPDF
import pathlib
import argparse
import os
import re
import json
import PIL


HIGHLIGHTED_SUFFIX = '_highlighted'

# get_text params
DEFAULT_FLAGS = None  # 0
DEFAULT_SORT = True

# clustered blocks params
DEFAULT_USE_CLUSTERED_BLOCKS = True
DEFAULT_X_TOLERANCE = 0
DEFAULT_Y_TOLERANCE = 3

# Adapted from cluster_drawings()
def cluster_blocks(
    page, clip=None, blocks=None, x_tolerance: float = 3, y_tolerance: float = 3
) -> list:
    """Join rectangles of neighboring vector graphic items.

    Args:
        clip: optional rect-like to restrict the page area to consider.
        blocks: (optional) output of a previous "get_drawings()".
        x_tolerance: horizontal neighborhood threshold.
        y_tolerance: vertical neighborhood threshold.

    Notes:
        Vector graphics (also called line-art or blocks) usually consist
        of independent items like rectangles, lines or curves to jointly
        form table grid lines or bar, line, pie charts and similar.
        This method identifies rectangles wrapping these disparate items.

    Returns:
        A list of Rect items, each wrapping line-art items that are close
        enough to be considered forming a common vector graphic.
        Only "significant" rectangles will be returned, i.e. having both,
        width and height larger than the tolerance values.
    """
    parea = page.rect  # the default clipping area
    if clip is not None:
        parea = Rect(clip)
    delta_x = x_tolerance  # shorter local name
    delta_y = y_tolerance  # shorter local name
    if blocks is None:  # if we cannot re-use a previous output
        blocks = page.get_text('dict', flags=DEFAULT_FLAGS, sort=DEFAULT_SORT)['blocks']

    def are_neighbors(r1, r2):
        """Detect whether r1, r2 are "neighbors".

        Items r1, r2 are called neighbors if the minimum distance between
        their points is less-equal delta.

        Both parameters must be (potentially invalid) rectangles.
        """
        # normalize rectangles as needed
        rr1_x0, rr1_x1 = (r1.x0, r1.x1) if r1.x1 > r1.x0 else (r1.x1, r1.x0)
        rr1_y0, rr1_y1 = (r1.y0, r1.y1) if r1.y1 > r1.y0 else (r1.y1, r1.y0)
        rr2_x0, rr2_x1 = (r2.x0, r2.x1) if r2.x1 > r2.x0 else (r2.x1, r2.x0)
        rr2_y0, rr2_y1 = (r2.y0, r2.y1) if r2.y1 > r2.y0 else (r2.y1, r2.y0)
        if (
            0
            or rr1_x1 < rr2_x0 - delta_x
            or rr1_x0 > rr2_x1 + delta_x
            or rr1_y1 < rr2_y0 - delta_y
            or rr1_y0 > rr2_y1 + delta_y
        ):
            # Rects do not overlap.
            return False
        else:
            # Rects overlap.
            return True

    # add bbox converted to rect
    for b in blocks: 
        bbox = b['bbox']
        b['rect'] = fitz.Rect(x0=bbox[0], y0=bbox[1], x1=bbox[2], y1=bbox[3])
    
    # exclude graphics not contained in the clip
    paths = [
        p
        for p in blocks
        if 1
        and p["rect"].x0 >= parea.x0
        and p["rect"].x1 <= parea.x1
        and p["rect"].y0 >= parea.y0
        and p["rect"].y1 <= parea.y1
    ]

    # list of all vector graphic rectangles
    prects = sorted([p["rect"] for p in paths], key=lambda r: (r.y1, r.x0))

    new_rects = []  # the final list of the joined rectangles

    # -------------------------------------------------------------------------
    # The strategy is to identify and join all rects that are neighbors
    # -------------------------------------------------------------------------
    while prects:  # the algorithm will empty this list
        r = +prects[0]  # copy of first rectangle
        repeat = True
        while repeat:
            repeat = False
            for i in range(len(prects) - 1, 0, -1):  # from back to front
                if are_neighbors(prects[i], r):
                    r |= prects[i].tl  # include in first rect
                    r |= prects[i].br  # include in first rect
                    del prects[i]  # delete this rect
                    repeat = True

        new_rects.append(r)
        del prects[0]
        prects = sorted(set(prects), key=lambda r: (r.y1, r.x0))

    new_rects = sorted(set(new_rects), key=lambda r: (r.y1, r.x0))
    return [r for r in new_rects if r.width > delta_x and r.height > delta_y]

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

def flags_decomposer(flags):
    """Make font flags human readable."""
    l = []
    if flags & 2 ** 0:
        l.append("superscript")
    if flags & 2 ** 1:
        l.append("italic")
    if flags & 2 ** 2:
        l.append("serifed")
    else:
        l.append("sans")
    if flags & 2 ** 3:
        l.append("monospaced")
    else:
        l.append("proportional")
    if flags & 2 ** 4:
        l.append("bold")
    return " ".join(l)



def highlight_sentences_in_pdf(pdf_document, use_clustered_blocks=DEFAULT_USE_CLUSTERED_BLOCKS, x_tolerance=DEFAULT_X_TOLERANCE, y_tolerance=DEFAULT_Y_TOLERANCE):

    pdf_data = []
    
    # Iterate through each page in the PDF
    for page_number in range(min(8, pdf_document.page_count)):
        page = pdf_document[page_number]
        
        text_models = []
        image_models = []
        block_models = []
        page_data = { 
            "page_number": page_number + 1,
            "page_width": page.rect[2] - page.rect[0],
            "page_height": page.rect[3] - page.rect[1],
            "texts_models_list": text_models,
            "blocks": block_models,
            "images_models_list": image_models,
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
                "left": bbox[0],
                "top": bbox[1],
                "end_left": bbox[2],
                "end_top": bbox[3],
                "image_width": image_info['width'],
                "image_height": image_info['height'],
            }
            image_models.append(image_model)
            
            # Save image
            #if image_info['xref']:
            #    image_data = pdf_document.extract_image(image_info['xref'])
            #    imgout = open(f"image{page_number}-{image_index}.{image_data['ext']}", "wb")
            #    imgout.write(image_data["image"])
            #    imgout.close()
        
            # for k in range(len(bbox)): bbox[k] += 2 if k < 2 else -2  # shrink bbox
            #highlight = page.add_rect_annot(bbox)
            #highlight.set_colors(stroke=[0, .2, 1])  # Blue rectangle
            #highlight.update()

        # Extract text with formatting information
        all_text_blocks = [block for block in page.get_text("dict", flags=DEFAULT_FLAGS, sort=DEFAULT_SORT)["blocks"] if block['type'] == 0]
                
        if use_clustered_blocks:
            page_data["use_clustered_blocks"] = {
                "x_tolerance": x_tolerance,
                "y_tolerance": y_tolerance,
            }
            clustered_rects = cluster_blocks(page, blocks=all_text_blocks, x_tolerance=x_tolerance, y_tolerance=y_tolerance)
            blocks = []
            print(f"all_text_blocks: {len(all_text_blocks)}  clustered_rects: {len(clustered_rects)}")
            for rect in clustered_rects:
                merged_blocks = [clipped_block for clipped_block in page.get_text("dict", clip=rect, flags=DEFAULT_FLAGS, sort=DEFAULT_SORT)["blocks"] if clipped_block['type'] == 0]
                # breakpoint()
                if len(merged_blocks) >= 1:
                    merged_block = merged_blocks[0]
                    for other_block in merged_blocks[1:]:
                        merged_block['lines'] += other_block['lines']
                        # breakpoint()
                        merged_rect = fitz.Rect(merged_block['bbox']) | fitz.Rect(other_block['bbox'])
                        merged_block['bbox'] = [merged_rect.x0, merged_rect.y0, merged_rect.x1, merged_rect.y1]
                    blocks.append(merged_block)
        else:
            page_data["use_clustered_blocks"] = False
            blocks = all_text_blocks
        
        print(f"blocks: {len(blocks)}")
        # breakpoint()
        
        # output.json
        #json_output = json.loads(page.get_text("json", sort=True))
        #with open('output.json', 'w') as f:
        #    json.dump(json_output, f, indent=2)
        
        for block_index, block in enumerate(blocks):
            if block['type'] == 0:  # Text block
                lines = block['lines']
                block_texts = []
                
                # Draw rectangles around each line
                for line_index, line in enumerate(lines):
                    spans = [span for span in line['spans'] if span['text']]
                    text = ''.join([span['text'] for span in spans])
                    # print(f"[page {page_number}] spans text in block {block_index} line {line_index}: '{text}'")
                    bbox = line['bbox']
                    
                    #highlight = page.add_rect_annot(bbox)
                    #highlight.set_colors(stroke=[1, 0, 0])  # Red rectangle
                    #highlight.update()
                    ## Add annotation with line text
                    #text_annot = page.add_text_annot((bbox[2]-2, bbox[3]-2), text, icon="Comment")
                    #text_annot.set_colors(stroke=[1, 0, 0])  # Red
                    #text_annot.update(opacity=.7)
                    
                    for span in spans:
                        # breakpoint()
                        text_model = {
                            "parent_block_number": block_index,
                            "original_text": span['text'],
                            "font_size": span['size'],
                            "font_family": span['font'],
                            "font_color": span['color'],
                            "font_color_hex": "#" + '{0:06X}'.format(span['color']),
                            "font_style": flags_decomposer(span['flags']),
                            "left": bbox[0],
                            "top": bbox[1],
                            "end_left": bbox[2],
                            "end_top": bbox[3],
                        }
                        text_models.append(text_model)
                    
                    block_texts.append(text)
                
                block_text = "\n".join(block_texts)

                block_model = {
                    "number": block_index,
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
        
        
    return pdf_data, pdf_document

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
    pdf_document = fitz.open(input_pdf)
    json_data, result_pdf_document = highlight_sentences_in_pdf(pdf_document)

    # Save the modified PDF to a new file
    result_pdf_document.save(output_pdf)
    result_pdf_document.close()

    print()
    print(f"use_clustered_blocks: {json_data[-1]['use_clustered_blocks']}")
    print(f"Highlighted PDF saved as: {output_pdf}")
    
    with open(output_json, 'w', encoding='utf-8') as f:
        json.dump(json_data, f, indent=2)
        print(f"JSON data saved as: {output_json}")

if __name__ == "__main__":
    main()
