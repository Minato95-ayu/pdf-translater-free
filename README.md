# Free PDF Translator

A free, local, and powerful PDF translator that preserves document layout and structure while translating to multiple languages.

## 🛠️ Tech Stack
- **Frontend**: React.js, Vite, TailwindCSS (for UI aesthetics), Lucide-react (Icons)
- **Backend**: FastAPI (Python), PyMuPDF (fitz) for PDF parsing, deep_translator (Google Translate API)
- **OCR**: OCR.space API (for extracting text from images inside the PDF)

## 💡 Step-wise Thinking & Architecture
The project is split into a modern React frontend and a robust Python backend to handle heavy PDF manipulations.

1. **Upload & UI (Frontend)**: The user drops a PDF file into a beautifully designed React interface and selects source/target languages.
2. **File Processing (Backend)**: The FastAPI server receives the file and uses `PyMuPDF` to parse all text blocks and their exact coordinates (`rect` bounding boxes).
3. **Translation**: The text is cleaned and sent to `deep_translator`. To optimize speed, texts are batched together so we aren't making thousands of API calls.
4. **Fallback OCR**: If a page is entirely an image with no parseable text, the backend automatically takes a snapshot of the page and uses the OCR.space API to read the text.
5. **Reconstruction**: The original text is covered up (white box overlay) and the new translated text is written in its exact place, dynamically adjusting font sizes to fit seamlessly.

## 🐛 Issues Faced & How We Fixed Them

### Issue 1: Text Overwriting & Column Bleeding
**Problem:** When translating to languages like Hindi (which require more horizontal space), the translated text would bleed into adjacent columns, overlapping and ruining the PDF layout.
**Solution:** The translation script originally forcibly expanded the width of the text blocks (e.g., `rect.x1 + 60`). We fixed this by strictly preserving the original width of the text column. If the text didn't fit, we implemented a smart fallback that incrementally shrinks the font size (down to 6pt) and only expands the height downwards (`y1`), preventing horizontal bleeding completely. We also separated the "erase" pass and "write" pass into two loops so newly translated text wouldn't be accidentally hidden by subsequent erasures.

### Issue 2: Unable to Share PDF on WhatsApp/Telegram
**Problem:** After downloading the translated PDF, mobile apps like WhatsApp would reject it as "unsupported" or corrupted.
**Solution:** PyMuPDF, when manipulating and erasing text, can leave a lot of unused references (dirty PDF structure). To fix this, we updated the backend's save function to use aggressive garbage collection and deflation compression (`doc.save(output_path, garbage=4, deflate=True)`). This cleans the PDF structure entirely, making it compliant and recognizable across all chat platforms.

## 🚀 Setup Instructions

### Backend Setup
```bash
cd backend
python -m venv venv
# Activate venv: .\venv\Scripts\activate (Windows) or source venv/bin/activate (Mac/Linux)
pip install fastapi uvicorn PyMuPDF deep-translator python-multipart requests
python -m uvicorn main:app --port 8000 --reload
```

### Frontend Setup
```bash
cd frontend
npm install
npm run dev
```

The app will be running at `http://localhost:5173`.
