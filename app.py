from flask import Flask, request, jsonify
import pdfplumber
import pytesseract
from pdf2image import convert_from_path
from PIL import Image, ImageEnhance
import os
import re

app = Flask(__name__)

# ==========================================
# 1. OCR এবং ইমেজ প্রসেসিং সেকশন
# ==========================================

def preprocess_image(img):
    img = img.convert('L')
    img = ImageEnhance.Contrast(img).enhance(2.0)
    img = ImageEnhance.Sharpness(img).enhance(2.0)
    return img

def extract_with_pdfplumber(pdf_path):
    full_text = []
    tables = []
    try:
        with pdfplumber.open(pdf_path) as pdf:
            for page in pdf.pages:
                text = page.extract_text()
                if text: full_text.append(text)
                page_tables = page.extract_tables()
                for table in page_tables:
                    if table: tables.append(table)
        
        table_text = []
        for table in tables:
            for row in table:
                cleaned_row = [str(cell) if cell else '' for cell in row]
                table_text.append('\t'.join(cleaned_row))
        return '\n\n'.join(full_text), '\n'.join(table_text)
    except Exception:
        return "", ""

def extract_with_pytesseract(pdf_path):
    """Extract text using pytesseract with memory optimization."""
    try:
        # Memory Optimization: DPI কমিয়ে 200 করা হলো এবং JPEG ফরম্যাট ব্যবহার করা হলো
        images = convert_from_path(pdf_path, dpi=200, fmt='jpeg') 
        
        full_text = []
        for img in images:
            # ইমেজ সাইজ ছোট করা (মেমোরি বাঁচাতে)
            if img.width > 2000:
                ratio = 2000 / float(img.width)
                new_height = int((float(img.height) * float(ratio)))
                img = img.resize((2000, new_height), Image.LANCZOS)

            img = preprocess_image(img)
            # Perform OCR
            text = pytesseract.image_to_string(img, lang='ben+eng')
            if text.strip():
                full_text.append(text)
                
        return '\n\n'.join(full_text)
    except Exception as e:
        print(f"pytesseract error: {e}")
        return ""

def clean_text(text):
    lines = text.splitlines()
    cleaned_lines = []
    seen = set()
    garbage_pattern = re.compile(r'[\d১-৯]*%')
    for line in lines:
        if garbage_pattern.search(line): continue
        if line.strip() and line not in seen:
            cleaned_lines.append(line)
            seen.add(line)
    return '\n'.join(cleaned_lines)

def merge_extractions(pdfplumber_text, pdfplumber_tables, pytesseract_text):
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
            if not found_better: merged_lines.append(line)
        else:
            merged_lines.append(line)
    return clean_text('\n'.join(merged_lines))

# ==========================================
# 2. ডাটা পার্সিং সেকশন (Code-1 & Code-2 Logic)
# ==========================================

def parse_patient_data(full_text):
    """টেক্সট থেকে নাম, RFID এবং ওষুধের লিস্ট বের করে"""
    
    # --- Extract Name ---
    name_match = re.search(r"(?:Patient\s+)?Name\s*[:\-]?\s*([A-Za-z\s]+)", full_text, re.IGNORECASE)
    patient_name = name_match.group(1).strip() if name_match else "Unknown"

    # --- Extract RFID ---
    rfid_match = re.search(r"RFID[:\s]*([A-Z0-9\-]+)", full_text, re.IGNORECASE)
    rfid = rfid_match.group(1).strip() if rfid_match else "RFID-UNKNOWN"

    # --- Extract Medicine Table ---
    medicine_table = []
    lines = full_text.split('\n')
    in_medicine_section = False
    
    for line in lines:
        if re.search(r'S/N.*Medicine.*Dose.*Duration', line, re.IGNORECASE):
            in_medicine_section = True
            continue
        
        if in_medicine_section and line.strip():
            parts = re.split(r'\t+|\s{2,}', line.strip())
            if len(parts) >= 4:
                medicine_table.append({
                    "S_N": parts[0].strip(),      # Firebase friendly keys
                    "Medicine": parts[1].strip(),
                    "Dose": parts[2].strip(),
                    "Duration": parts[3].strip()
                })
            elif len(parts) == 0 or (len(parts) == 1 and not parts[0]):
                in_medicine_section = False

    return {
        "RFID_Tag": rfid,
        "Patient_Name": patient_name,
        "Medicine_Table": medicine_table
    }

# ==========================================
# 3. API Endpoints
# ==========================================

@app.route('/', methods=['GET'])
def home():
    return "Smart Prescription API is Running!"

@app.route('/convert', methods=['POST'])
def convert_pdf():
    if 'file' not in request.files:
        return jsonify({'error': 'No file part'}), 400
    
    file = request.files['file']
    if file.filename == '':
        return jsonify({'error': 'No selected file'}), 400

    if file:
        try:
            # টেম্পোরারি ফাইল সেভ
            temp_path = "/tmp/upload.pdf"
            file.save(temp_path)
            
            # স্টেপ ১: OCR করা
            p_text, p_tables = extract_with_pdfplumber(temp_path)
            t_text = extract_with_pytesseract(temp_path)
            raw_merged_text = merge_extractions(p_text, p_tables, t_text)
            
            # স্টেপ ২: ডাটা পার্স করা (স্ট্রাকচার্ড ডাটা বানানো)
            structured_data = parse_patient_data(raw_merged_text)
            
            # টেম্পোরারি ফাইল ক্লিন
            if os.path.exists(temp_path):
                os.remove(temp_path)

            # স্টেপ ৩: ক্লিন JSON রিটার্ন করা
            return jsonify({
                'status': 'success',
                'raw_text': raw_merged_text, # ডিবাগিংয়ের জন্য পুরো টেক্সটও রাখলাম
                'data': structured_data      # এটিই আপনার আসল দরকারি ডাটা
            })
            
        except Exception as e:
            return jsonify({'error': str(e)}), 500

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000)
