from flask import Flask, request, jsonify
import pdfplumber
import pytesseract
from pdf2image import convert_from_path
from PIL import Image, ImageEnhance
import os
import re

app = Flask(__name__)

# --- আপনার লজিক ফাংশনগুলো (অপরিবর্তিত) ---

def preprocess_image(img):
    """Preprocess image for better OCR accuracy."""
    img = img.convert('L')
    img = ImageEnhance.Contrast(img).enhance(2.0)
    img = ImageEnhance.Sharpness(img).enhance(2.0)
    return img

def extract_with_pdfplumber(pdf_path):
    """Extract text and tables using pdfplumber."""
    full_text = []
    tables = []
    try:
        with pdfplumber.open(pdf_path) as pdf:
            for page in pdf.pages:
                text = page.extract_text()
                if text:
                    full_text.append(text)
                
                page_tables = page.extract_tables()
                for table in page_tables:
                    if table:
                        tables.append(table)
        
        table_text = []
        for table in tables:
            for row in table:
                cleaned_row = [str(cell) if cell else '' for cell in row]
                table_text.append('\t'.join(cleaned_row))
        
        return '\n\n'.join(full_text), '\n'.join(table_text)
    except Exception as e:
        print(f"pdfplumber error: {e}")
        return "", ""

def extract_with_pytesseract(pdf_path):
    """Extract text using pytesseract with image preprocessing."""
    try:
        # Render/Docker এ poppler পাথ অটোমেটিক সেট থাকে
        images = convert_from_path(pdf_path)
        full_text = []
        for img in images:
            img = preprocess_image(img)
            # Perform OCR with Bangla + English
            text = pytesseract.image_to_string(img, lang='ben+eng')
            if text.strip():
                full_text.append(text)
        return '\n\n'.join(full_text)
    except Exception as e:
        print(f"pytesseract error: {e}")
        return ""

def clean_text(text):
    """Remove garbled text and duplicates."""
    lines = text.splitlines()
    cleaned_lines = []
    seen = set()
    garbage_pattern = re.compile(r'[\d১-৯]*%')
    
    for line in lines:
        if garbage_pattern.search(line):
            continue
        if line.strip() and line not in seen:
            cleaned_lines.append(line)
            seen.add(line)
    return '\n'.join(cleaned_lines)

def merge_extractions(pdfplumber_text, pdfplumber_tables, pytesseract_text):
    """Merge outputs prioritizing tables and Bangla."""
    pdfplumber_text = clean_text(pdfplumber_text)
    pytesseract_text = clean_text(pytesseract_text)
    
    pdfplumber_lines = pdfplumber_text.splitlines()
    pytesseract_lines = pytesseract_text.splitlines()
    table_lines = pdfplumber_tables.splitlines()
    
    merged_lines = []
    bangla_pattern = re.compile(r'[\u0980-\u09FF]+')
    
    medicine_section = False
    for line in pdfplumber_lines:
        if 'S/N' in line or 'Medicine' in line:
            medicine_section = True
            merged_lines.extend(table_lines)
            continue
        if medicine_section and not line.strip():
            medicine_section = False
            continue
        
        if bangla_pattern.search(line):
            found_better = False
            for t_line in pytesseract_lines:
                if bangla_pattern.search(t_line) and any(word in t_line for word in line.split()):
                    merged_lines.append(t_line)
                    found_better = True
                    break
            if not found_better:
                merged_lines.append(line)
        else:
            merged_lines.append(line)
    
    return clean_text('\n'.join(merged_lines))

# --- API Endpoint (সার্ভার কন্ট্রোলার) ---

@app.route('/', methods=['GET'])
def home():
    return "PDF OCR API is Running! Send POST request to /convert"

@app.route('/convert', methods=['POST'])
def convert_pdf():
    # ১. ফাইল চেক করা
    if 'file' not in request.files:
        return jsonify({'error': 'No file part'}), 400
    
    file = request.files['file']
    if file.filename == '':
        return jsonify({'error': 'No selected file'}), 400

    if file:
        try:
            # ২. টেম্পোরারি ফোল্ডারে ফাইল সেভ করা (কারণ আপনার কোড ফাইল পাথ চায়)
            temp_path = "/tmp/temp_upload.pdf"
            file.save(temp_path)
            
            # ৩. আপনার লজিক ফাংশনগুলো কল করা
            pdfplumber_text, pdfplumber_tables = extract_with_pdfplumber(temp_path)
            pytesseract_text = extract_with_pytesseract(temp_path)
            
            final_text = merge_extractions(pdfplumber_text, pdfplumber_tables, pytesseract_text)
            
            # ৪. টেম্পোরারি ফাইল ডিলিট করা (মেমোরি বাঁচাতে)
            if os.path.exists(temp_path):
                os.remove(temp_path)

            # ৫. রেজাল্ট ফেরত পাঠানো (JSON)
            return jsonify({
                'status': 'success',
                'filename': file.filename,
                'text': final_text
            })
            
        except Exception as e:
            return jsonify({'error': str(e)}), 500

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000)
