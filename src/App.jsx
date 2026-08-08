import { useState, useRef, useEffect } from 'react';
import { UploadCloud, FileText, Loader2, CheckCircle, Download, RefreshCw } from 'lucide-react';
import './index.css';
import logo from './assets/logo.png';

const LANGUAGES = [
  { code: 'hi', name: 'Hindi' },
  { code: 'es', name: 'Spanish' },
  { code: 'fr', name: 'French' },
  { code: 'de', name: 'German' },
  { code: 'zh-CN', name: 'Chinese (Simplified)' },
  { code: 'ar', name: 'Arabic' },
  { code: 'ru', name: 'Russian' },
  { code: 'ja', name: 'Japanese' },
  { code: 'ko', name: 'Korean' },
  { code: 'it', name: 'Italian' },
  { code: 'pt', name: 'Portuguese' },
  { code: 'en', name: 'English' }
];

function App() {
  const [file, setFile] = useState(null);
  const [isDragging, setIsDragging] = useState(false);
  const [sourceLang, setSourceLang] = useState('auto');
  const [targetLang, setTargetLang] = useState('hi');
  const [status, setStatus] = useState('idle'); // idle, translating, success, error
  const [downloadUrl, setDownloadUrl] = useState('');
  const [fileName, setFileName] = useState('');
  const fileInputRef = useRef(null);

  const DIRECT_URL = 'https://pdf-translator-backend-av6m.onrender.com';
  const PROXY_URL = '/api';

  // Wake up the Render backend immediately when the page loads
  useEffect(() => {
    fetch(DIRECT_URL + '/').catch(() => {
      // Direct blocked (adblocker), try via proxy
      fetch(PROXY_URL + '/').catch(() => {});
    });
  }, []);

  const handleDragOver = (e) => {
    e.preventDefault();
    setIsDragging(true);
  };

  const handleDragLeave = (e) => {
    e.preventDefault();
    setIsDragging(false);
  };

  const handleDrop = (e) => {
    e.preventDefault();
    setIsDragging(false);
    
    if (e.dataTransfer.files && e.dataTransfer.files[0]) {
      const droppedFile = e.dataTransfer.files[0];
      if (droppedFile.type === 'application/pdf') {
        if (droppedFile.size > 20 * 1024 * 1024) {
          alert("File is too large. Maximum size is 20MB.");
          return;
        }
        setFile(droppedFile);
        setStatus('idle');
      } else {
        alert("Please upload a PDF file.");
      }
    }
  };

  const handleFileChange = (e) => {
    if (e.target.files && e.target.files[0]) {
      const selectedFile = e.target.files[0];
      if (selectedFile.size > 20 * 1024 * 1024) {
        alert("File is too large. Maximum size is 20MB.");
        e.target.value = null;
        return;
      }
      setFile(selectedFile);
      setStatus('idle');
    }
  };

  const handleSwapLanguages = () => {
    if (sourceLang === 'auto') {
      setSourceLang(targetLang);
      setTargetLang('en');
    } else {
      const temp = sourceLang;
      setSourceLang(targetLang);
      setTargetLang(temp);
    }
  };

  const handleTranslate = async () => {
    if (!file) return;
    
    setStatus('translating');
    const formData = new FormData();
    formData.append('file', file);
    formData.append('target_lang', targetLang);
    formData.append('source_lang', sourceLang);

    const processResponse = async (response) => {
      if (!response.ok) {
        const text = await response.text().catch(() => '');
        throw new Error(`Server error ${response.status}: ${text || 'Translation failed'}`);
      }
      const blob = await response.blob();
      if (blob.type === 'application/json') {
        const text = await blob.text();
        const data = JSON.parse(text);
        if (data.error) throw new Error(data.error);
      }
      return blob;
    };

    try {
      let blob;

      // Strategy: Try direct URL first (no timeout limit, fast)
      // If adblocker blocks it, fall back to Vercel proxy
      try {
        const response = await fetch(DIRECT_URL + '/translate', {
          method: 'POST',
          body: formData,
        });
        blob = await processResponse(response);
      } catch (directError) {
        // Direct failed (likely adblocker) — retry through Vercel proxy
        console.warn('Direct URL failed, retrying via proxy:', directError.message);
        
        // Need fresh FormData because the previous one was consumed
        const retryFormData = new FormData();
        retryFormData.append('file', file);
        retryFormData.append('target_lang', targetLang);
        retryFormData.append('source_lang', sourceLang);

        const response = await fetch(PROXY_URL + '/translate', {
          method: 'POST',
          body: retryFormData,
        });
        blob = await processResponse(response);
      }

      const url = window.URL.createObjectURL(blob);
      setDownloadUrl(url);
      setFileName(`translated_${targetLang}_${file.name}`);
      setStatus('success');
    } catch (error) {
      console.error('Translation failed:', error);
      setStatus('error');
      alert(error.message || "An error occurred during translation. Please try again.");
    }
  };

  const handleReset = () => {
    setFile(null);
    setStatus('idle');
    setDownloadUrl('');
    setFileName('');
  };

  return (
    <>
      <div className="bg-orb orb-1"></div>
      <div className="bg-orb orb-2"></div>
      
      <div className="app-container">
        <header className="header" style={{ display: 'flex', flexDirection: 'column', alignItems: 'center' }}>
          <img src={logo} alt="Logo" style={{ width: '80px', height: '80px', marginBottom: '1rem', borderRadius: '16px', boxShadow: '0 4px 20px rgba(0, 0, 0, 0.2)' }} />
          <h1 className="title">Free PDF Translator</h1>
          <p className="subtitle">Translate your documents instantly, for free, while preserving layout.</p>
        </header>

        <main className="glass-card">
          {status === 'success' ? (
            <div className="success-container">
              <CheckCircle className="success-icon" />
              <h2 className="success-title">Translation Complete!</h2>
              <p className="success-text">Your document has been successfully translated.</p>
              
              <a href={downloadUrl} download={fileName} style={{ textDecoration: 'none' }}>
                <button className="btn">
                  <Download size={20} />
                  Download Translated PDF
                </button>
              </a>
              
              <button className="btn btn-secondary" onClick={handleReset}>
                <RefreshCw size={20} />
                Translate Another File
              </button>
            </div>
          ) : (
            <>
              <div className="controls-row">
                <div className="input-group" style={{ flex: 2 }}>
                  <label className="label">Upload Document</label>
                  <div 
                    className={`dropzone ${isDragging ? 'active' : ''}`}
                    onDragOver={handleDragOver}
                    onDragLeave={handleDragLeave}
                    onDrop={handleDrop}
                    onClick={() => fileInputRef.current?.click()}
                  >
                    {file ? (
                      <>
                        <FileText className="dropzone-icon" />
                        <div className="dropzone-text">{file.name}</div>
                        <div className="dropzone-subtext">{(file.size / 1024 / 1024).toFixed(2)} MB • Click to change</div>
                      </>
                    ) : (
                      <>
                        <UploadCloud className="dropzone-icon" />
                        <div className="dropzone-text">Click to upload or drag and drop</div>
                        <div className="dropzone-subtext">PDF files only (Max 20MB)</div>
                      </>
                    )}
                    <input 
                      type="file" 
                      ref={fileInputRef} 
                      onChange={handleFileChange} 
                      accept=".pdf" 
                      className="file-input" 
                    />
                  </div>
                </div>

                <div className="input-group" style={{ flex: 1, justifyContent: 'flex-start', display: 'flex', flexDirection: 'column', gap: '1rem' }}>
                  <div className="input-group" style={{ gap: '0.5rem' }}>
                    <label className="label">Source Language</label>
                    <select 
                      className="select-input"
                      value={sourceLang}
                      onChange={(e) => setSourceLang(e.target.value)}
                    >
                      <option value="auto">Auto Detect</option>
                      {LANGUAGES.map(lang => (
                        <option key={lang.code} value={lang.code}>
                          {lang.name}
                        </option>
                      ))}
                    </select>
                  </div>

                  <div style={{ display: 'flex', justifyContent: 'center', margin: '-0.5rem 0' }}>
                    <button 
                      className="btn" 
                      style={{ padding: '0.5rem', borderRadius: '50%', width: '40px', height: '40px', display: 'flex', alignItems: 'center', justifyContent: 'center', background: 'rgba(255,255,255,0.1)' }}
                      onClick={handleSwapLanguages}
                      title="Swap Languages"
                    >
                      <RefreshCw size={18} />
                    </button>
                  </div>

                  <div className="input-group" style={{ gap: '0.5rem' }}>
                    <label className="label">Target Language</label>
                    <select 
                      className="select-input"
                      value={targetLang}
                      onChange={(e) => setTargetLang(e.target.value)}
                    >
                      {LANGUAGES.map(lang => (
                        <option key={lang.code} value={lang.code}>
                          {lang.name}
                        </option>
                      ))}
                    </select>
                  </div>
                </div>
              </div>

              <button 
                className="btn" 
                onClick={handleTranslate} 
                disabled={!file || status === 'translating'}
              >
                {status === 'translating' ? (
                  <>
                    <Loader2 className="loading-spinner" size={20} />
                    Translating... Please wait
                  </>
                ) : (
                  'Translate PDF Now'
                )}
              </button>
            </>
          )}
        </main>
      </div>
    </>
  );
}

export default App;
