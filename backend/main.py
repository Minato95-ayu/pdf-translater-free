from fastapi import FastAPI, File, UploadFile, Form, BackgroundTasks
from fastapi.responses import FileResponse
from fastapi.middleware.cors import CORSMiddleware
import fitz  # PyMuPDF
from deep_translator import GoogleTranslator
import os
import shutil
import uuid
import requests
import base64
from concurrent.futures import ThreadPoolExecutor, as_completed
from langdetect import detect

app = FastAPI(title="Free PDF Translator API")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

UPLOAD_DIR = "uploads"
OUTPUT_DIR = "outputs"
os.makedirs(UPLOAD_DIR, exist_ok=True)
os.makedirs(OUTPUT_DIR, exist_ok=True)

def ocr_image(image_bytes):
    """Uses OCR.space free API to extract text from image bytes"""
    payload = {
        'isOverlayRequired': False,
        'apikey': 'helloworld',
        'language': 'eng'
    }
    try:
        b64 = base64.b64encode(image_bytes).decode('utf-8')
        payload['base64Image'] = 'data:image/png;base64,' + b64
        r = requests.post('https://api.ocr.space/parse/image', data=payload, timeout=20)
        res = r.json()
        if not res.get('IsErroredOnProcessing') and res.get('ParsedResults'):
            return res['ParsedResults'][0]['ParsedText']
    except Exception as e:
        print(f"OCR Error: {e}")
    return ""

def fast_batch_translate(texts: list, target_lang: str, source_lang: str = 'auto'):
    if not texts: return {}
    translator = GoogleTranslator(source=source_lang, target=target_lang)
    batches = []
    current_batch = []
    current_len = 0
    import re
    
    # Pre-filter to avoid translating single English letters, numbers, or simple markers (e.g. "A", "B", "1. A")
    to_translate = []
    translated_map = {}
    for t in texts:
        clean_t = t.replace('\n', ' ').strip()
        if not clean_t: continue
        
        is_math = False
        alpha_chars = len(re.findall(r'[^\W\d_]', clean_t))
        total_chars = len(clean_t)
        has_words = bool(re.search(r'[^\W\d_]{3,}', clean_t))
        has_math_ops = bool(re.search(r'[=\+\-\*/\^]', clean_t))
        
        if total_chars > 0:
            if (alpha_chars / total_chars < 0.4) or (has_math_ops and not has_words) or (not has_words and alpha_chars < 5):
                is_math = True
                
        if is_math:
            translated_map[t] = t
        else:
            to_translate.append(t)
            
    for t in to_translate:
        clean_t = t.replace('\n', ' ').strip()
        if current_len + len(clean_t) + 5 > 4000:
            batches.append(current_batch)
            current_batch = [clean_t]
            current_len = len(clean_t)
        else:
            current_batch.append(clean_t)
            current_len += len(clean_t) + 5
    if current_batch:
        batches.append(current_batch)
        
    def process_batch(batch):
        joined = "\n\n".join(batch)
        try:
            res = translator.translate(joined)
            parts = [p.strip() for p in res.split('\n\n')]
            if len(parts) == len(batch):
                for orig, trans in zip(batch, parts):
                    translated_map[orig] = trans
            else:
                for orig in batch:
                    try:
                        translated_map[orig] = translator.translate(orig)
                    except:
                        translated_map[orig] = orig
        except:
            for orig in batch:
                try:
                    translated_map[orig] = translator.translate(orig)
                except:
                    translated_map[orig] = orig

    with ThreadPoolExecutor(max_workers=10) as executor:
        futures = [executor.submit(process_batch, b) for b in batches]
        for f in as_completed(futures):
            pass
            
    return translated_map

def translate_pdf_task(input_path: str, output_path: str, target_lang: str, source_lang: str):
    try:
        doc = fitz.open(input_path)
        
        if source_lang != 'auto':
            sample_text = ""
            for page in doc:
                text = page.get_text()
                if text.strip():
                    sample_text += text + " "
                if len(sample_text) > 500:
                    break
            
            if len(sample_text.strip()) > 20:
                try:
                    detected_lang = detect(sample_text)
                    if detected_lang == 'zh-cn':
                        detected_lang = 'zh-CN'
                    # langdetect 'en' matches our 'en', 'hi' matches our 'hi'
                    # If mismatch, raise specific error
                    if detected_lang != source_lang:
                        raise Exception("diya gya laungues information match nahi kar raah")
                except Exception as e:
                    if str(e) == "diya gya laungues information match nahi kar raah":
                        raise e

        font_path = "font.ttf"
        
        for page in doc:
            if os.path.exists(font_path):
                page.insert_font(fontname="noto", fontfile=font_path)
            else:
                fontname = "helv" # fallback
            
            used_font = "noto" if os.path.exists(font_path) else "helv"

            text_dict = page.get_text("dict")
            text_blocks = []
            for b in text_dict.get("blocks", []):
                if b.get("type") == 0:
                    cols = []
                    for l in b.get("lines", []):
                        matched_col = None
                        for col in cols:
                            col_x0 = min([cline["bbox"][0] for cline in col])
                            col_x1 = max([cline["bbox"][2] for cline in col])
                            if not (l["bbox"][2] < col_x0 - 10 or l["bbox"][0] > col_x1 + 10):
                                matched_col = col
                                break
                        if matched_col is not None:
                            matched_col.append(l)
                        else:
                            cols.append([l])
                    
                    for col_lines in cols:
                        col_lines.sort(key=lambda x: x["bbox"][1])
                        font_sizes = []
                        colors = []
                        text = ""
                        for i, l in enumerate(col_lines):
                            line_text = ""
                            for s in l.get("spans", []):
                                font_sizes.append(s.get("size", 11))
                                colors.append(s.get("color", 0))
                                line_text += s.get("text", "")
                            text += line_text
                            if i < len(col_lines) - 1:
                                text += "\n"
                        
                        med_size = sorted(font_sizes)[len(font_sizes)//2] if font_sizes else 11
                        from collections import Counter
                        most_common_color = Counter(colors).most_common(1)[0][0] if colors else 0
                        hex_color = "#{:06x}".format(most_common_color & 0xFFFFFF)
                        
                        if len(text.strip()) >= 2:
                            bbox = [
                                min([l["bbox"][0] for l in col_lines]),
                                min([l["bbox"][1] for l in col_lines]),
                                max([l["bbox"][2] for l in col_lines]),
                                max([l["bbox"][3] for l in col_lines])
                            ]
                            text_blocks.append((bbox[0], bbox[1], bbox[2], bbox[3], text, med_size, hex_color))
            
            if len(text_blocks) == 0:
                print("No text found, running OCR on page image...")
                pix = page.get_pixmap(dpi=150)
                img_bytes = pix.tobytes("png")
                extracted_text = ocr_image(img_bytes)
                
                if extracted_text and len(extracted_text.strip()) > 2:
                    try:
                        translated_text = GoogleTranslator(source=source_lang, target=target_lang).translate(extracted_text)
                    except:
                        translated_text = extracted_text
                    page.add_redact_annot(page.rect, fill=(1, 1, 1))
                    page.apply_redactions(images=0)
                    text_rect = fitz.Rect(20, 20, page.rect.width - 20, page.rect.height - 20)
                    css = f"@font-face {{ font-family: 'noto'; src: url('font.ttf'); }} * {{ font-family: 'noto', sans-serif; }}"
                    html = f"<style>{css}</style><div style=\"font-size: 12pt; color: black; line-height: 1.2;\">{translated_text}</div>"
                    archive = fitz.Archive(os.path.dirname(os.path.abspath(__file__)))
                    page.insert_htmlbox(text_rect, html, archive=archive, scale_low=0.1)
                continue
            
            unique_texts = list(set([b[4].replace('\n', ' ').strip() for b in text_blocks if b[4].strip()]))
            translated_map = fast_batch_translate(unique_texts, target_lang, source_lang)
            
            blocks_to_translate = []
            for block in text_blocks:
                orig_text = block[4].replace('\n', ' ').strip()
                translated_text = translated_map.get(orig_text, orig_text)
                if translated_text != orig_text:
                    blocks_to_translate.append((block, orig_text, translated_text))
            
            # First pass: Erase only translated text rectangles
            for block, _, _ in blocks_to_translate:
                rect = fitz.Rect(block[:4])
                page.add_redact_annot(rect, fill=(1, 1, 1))
                
            page.apply_redactions(images=0)

            # Second pass: Insert translated text
            archive = fitz.Archive(os.path.dirname(os.path.abspath(__file__)))
            css = f"@font-face {{ font-family: 'noto'; src: url('font.ttf'); }} * {{ font-family: 'noto', sans-serif; }}"
            
            for block, orig_text, translated_text in blocks_to_translate:
                rect = fitz.Rect(block[:4])
                med_size = block[5]
                hex_color = block[6]
                
                # Strictly preserve the original bounding box to avoid overlapping with adjacent blocks
                write_rect = fitz.Rect(rect.x0, rect.y0, rect.x1, rect.y1)
                
                html = f"<style>{css}</style><div style=\"font-size: {med_size}pt; color: {hex_color}; line-height: 1.2;\">{translated_text}</div>"
                # scale_low=0.1 automatically scales down font size until it fits
                page.insert_htmlbox(write_rect, html, archive=archive, scale_low=0.1)
                    
        doc.save(output_path, garbage=4, deflate=True)
        doc.close()
    except Exception as e:
        if str(e) == "diya gya laungues information match nahi kar raah":
            raise e
        print(f"Failed to process PDF: {e}")

from fastapi.staticfiles import StaticFiles
app.mount("/outputs", StaticFiles(directory=OUTPUT_DIR), name="outputs")

@app.post("/translate")
async def translate_pdf_endpoint(
    file: UploadFile = File(...),
    target_lang: str = Form("en"),
    source_lang: str = Form("auto")
):
    file_id = str(uuid.uuid4())
    input_path = os.path.join(UPLOAD_DIR, f"{file_id}_{file.filename}")
    output_filename = f"translated_{file_id}.pdf"
    output_path = os.path.join(OUTPUT_DIR, output_filename)
    
    with open(input_path, "wb") as buffer:
        shutil.copyfileobj(file.file, buffer)
        
    try:
        translate_pdf_task(input_path, output_path, target_lang, source_lang)
    except Exception as e:
        if str(e) == "diya gya laungues information match nahi kar raah":
            return {"error": str(e)}
    
    if not os.path.exists(output_path):
        return {"error": "Failed to translate PDF"}
        
    from fastapi.responses import FileResponse
    return FileResponse(
        path=output_path, 
        filename=f"translated_{file.filename}",
        media_type='application/pdf'
    )

@app.get("/")
def read_root():
    return {"message": "PDF Translator API is running!"}
