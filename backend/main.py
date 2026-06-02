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
    import re
    
    # Pre-filter to avoid translating single English letters, numbers, or simple markers (e.g. "A", "B", "1. A")
    to_translate = []
    translated_map = {}
    for t in texts:
        clean_t = t.replace('\n', ' ').strip()
        if not clean_t: continue
        # Skip translation for single characters or markers like "1. A", or purely numeric/symbols
        if (len(clean_t) == 1 and clean_t.isascii() and clean_t.isalpha()) or \
           re.match(r'^\d+\.?\s*[a-zA-Z]$', clean_t) or \
           re.match(r'^[\d\s\W]+$', clean_t):
            translated_map[t] = t
        else:
            to_translate.append(t)
            
    def process_item(t):
        try:
            return t, translator.translate(t)
        except:
            return t, t

    with ThreadPoolExecutor(max_workers=10) as executor:
        futures = [executor.submit(process_item, t) for t in to_translate]
        for f in as_completed(futures):
            orig, trans = f.result()
            translated_map[orig] = trans
            
    return translated_map

def translate_pdf_task(input_path: str, output_path: str, target_lang: str, source_lang: str):
    try:
        doc = fitz.open(input_path)
        font_path = "font.ttf"
        
        for page in doc:
            if os.path.exists(font_path):
                page.insert_font(fontname="noto", fontfile=font_path)
            else:
                fontname = "helv" # fallback
            
            used_font = "noto" if os.path.exists(font_path) else "helv"

            blocks = page.get_text("blocks")
            text_blocks = [b for b in blocks if b[6] == 0 and len(b[4].strip()) >= 2]
            
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
                    page.draw_rect(page.rect, color=(1, 1, 1), fill=(1, 1, 1))
                    text_rect = fitz.Rect(20, 20, page.rect.width - 20, page.rect.height - 20)
                    css = f"@font-face {{ font-family: 'noto'; src: url('font.ttf'); }} * {{ font-family: 'noto', sans-serif; }}"
                    html = f"<style>{css}</style><div style=\"font-size: 12pt; color: black; line-height: 1.2;\">{translated_text}</div>"
                    archive = fitz.Archive(os.path.dirname(os.path.abspath(__file__)))
                    page.insert_htmlbox(text_rect, html, archive=archive, scale_low=0.1)
                continue
            
            unique_texts = list(set([b[4].replace('\n', ' ').strip() for b in text_blocks if b[4].strip()]))
            translated_map = fast_batch_translate(unique_texts, target_lang, source_lang)
            
            # First pass: Erase all original text rectangles
            for block in text_blocks:
                rect = fitz.Rect(block[:4])
                page.draw_rect(rect, color=(1, 1, 1), fill=(1, 1, 1))

            # Second pass: Insert translated text
            archive = fitz.Archive(os.path.dirname(os.path.abspath(__file__)))
            css = f"@font-face {{ font-family: 'noto'; src: url('font.ttf'); }} * {{ font-family: 'noto', sans-serif; }}"
            
            for block in text_blocks:
                rect = fitz.Rect(block[:4])
                orig_text = block[4].replace('\n', ' ').strip()
                translated_text = translated_map.get(orig_text, orig_text)
                
                # Strictly preserve the original width to avoid column overlapping
                # Give a little extra height to accommodate line height differences
                write_rect = fitz.Rect(rect.x0, rect.y0, rect.x1, rect.y1 + 10)
                
                html = f"<style>{css}</style><div style=\"font-size: 11pt; color: black; line-height: 1.1;\">{translated_text}</div>"
                # scale_low=0.1 automatically scales down font size until it fits
                page.insert_htmlbox(write_rect, html, archive=archive, scale_low=0.1)
                    
        doc.save(output_path, garbage=4, deflate=True)
        doc.close()
    except Exception as e:
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
        
    translate_pdf_task(input_path, output_path, target_lang, source_lang)
    
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
