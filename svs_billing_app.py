import customtkinter as ctk
from tkinter import messagebox
import tkinter as tk
from tkinter import ttk
import sqlite3
from datetime import datetime, timedelta
import json
import os
from reportlab.lib.pagesizes import letter
from reportlab.pdfgen import canvas
from reportlab.lib.units import inch
from reportlab.lib import colors
# ReportLab Font Registration Imports
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
# Pathlib and frozen app support
from pathlib import Path
import sys
import re

# Support PyInstaller/standalone executable resource paths.
# When PyInstaller bundles the app, it extracts files to a temporary folder
# and sets sys._MEIPASS. Use BASE_PATH for all resource lookups so fonts,
# DB and other data are found both when running normally and when frozen.
if getattr(sys, 'frozen', False):
    BASE_PATH = getattr(sys, '_MEIPASS', os.path.dirname(__file__))
else:
    BASE_PATH = os.path.dirname(__file__)
# Try to use WeasyPrint (HTML -> PDF) for correct complex-script shaping (preferred)
try:
    from weasyprint import HTML
    WEASY_AVAILABLE = True
except Exception:
    WEASY_AVAILABLE = False

# --- CONFIGURATION & DATABASE SETUP ---
DB_NAME = os.getenv('DB_NAME', 'svs_sales_db.db')
# Use environment variables or placeholders to avoid committing personal data
COMPANY_NAME = os.getenv('COMPANY_NAME', 'Your Company')
COMPANY_ADDRESS = os.getenv('COMPANY_ADDRESS', 'Your Address, City')
COMPANY_PHONE = os.getenv('COMPANY_PHONE', '')

# --- UI THEME (unique style: dark navy + saffron accent) ---
THEME_BG = "#0ADAFF"            # deep navy background
THEME_MAIN = "#000000"          # main content background
THEME_SIDEBAR = "#000000"       # sidebar background
THEME_ACCENT = "#00bdf1"        # saffron / accent color
THEME_ACCENT_HOVER = "#ffb07a"  # lighter accent for hover
THEME_TEXT = "#e6edf3"          # primary text color
THEME_MUTED = "#9aa6b2"         # muted text
THEME_BUTTON_TEXT = "#000000"   # dark text for light buttons (used selectively)


# Utility: create a safe PDF filename using the customer name and timestamp
def make_pdf_filename(customer: str | None = None, fallback: str | None = None) -> str:
    """Return a path like: Invoices/Customer Name - YYYY-MM-DD - HH-MM-SS.pdf

    Removes characters not allowed in filenames and trims length.
    """
    name = (customer or fallback or 'Invoice').strip()
    # Remove filesystem-unfriendly characters \ / : * ? " < > |
    name = re.sub(r'[\\/:*?"<>|]', '', name)
    if not name:
        name = 'Invoice'
    # Limit length to avoid excessively long filenames
    if len(name) > 80:
        name = name[:80].rstrip()
    timestamp = datetime.now().strftime('%Y-%m-%d - %H-%M-%S')
    safe_filename = f"{name} - {timestamp}.pdf"
    return os.path.join('Invoices', safe_filename)


# --- 🎯 TAMIL FONT CONFIGURATION (Required for Tamil in PDF) ---
# Locate a Tamil TTF inside the bundled `Noto_Sans_Tamil` folder (if present).
# This makes the app work out-of-the-box when the repository includes the font.
PDF_FONT_NAME = 'TamilFont'
PDF_FONT_FILE = None

# Look for font files (.ttf or .otf) in a few likely places including repo root.
# Prefer files with 'vanavil', 'noto', 'tamil', 'lohit' in the name.
_candidate_dirs = [
    os.path.join(BASE_PATH),
    os.path.join(BASE_PATH, 'Noto_Sans_Tamil'),
    os.path.join(BASE_PATH, 'Noto_Sans_Tamil', 'static'),
    os.path.join(BASE_PATH, 'NotoSansTamil'),
]
_font_dir = None
font_candidates = []
for d in _candidate_dirs:
    if os.path.isdir(d):
        files = [f for f in os.listdir(d) if f.lower().endswith(('.ttf', '.otf'))]
        if files:
            _font_dir = d
            font_candidates = files
            break

if _font_dir is None:
    # As a last attempt, check current working directory
    pwd = os.getcwd()
    files = [f for f in os.listdir(pwd) if f.lower().endswith(('.ttf', '.otf'))]
    if files:
        _font_dir = pwd
        font_candidates = files

if font_candidates:
    # exact filename preference
    preferred_names = [
        'vanavil-avvaiyar regular.otf',
        'notosanstamil-variablefont_wdth,wght.ttf',
        'notosanstamil-variablefont_wdth,wght.ttf',
        'lohit-tamil.ttf',
    ]
    chosen = None
    low_candidates = [f.lower() for f in font_candidates]
    for pn in preferred_names:
        if pn.lower() in low_candidates:
            chosen = font_candidates[low_candidates.index(pn.lower())]
            break
    if not chosen:
        for f in font_candidates:
            ln = f.lower()
            if any(k in ln for k in ('vanavil', 'noto', 'tamil', 'lohit')):
                chosen = f
                break
    if not chosen:
        chosen = font_candidates[0]
    PDF_FONT_FILE = os.path.join(_font_dir or BASE_PATH, chosen)


if PDF_FONT_FILE is None or not os.path.exists(PDF_FONT_FILE):
    # Look for font in the PyInstaller _MEIPASS directory when running as exe
    if getattr(sys, 'frozen', False):
        meipass_font = os.path.join(BASE_PATH, 'Noto_Sans_Tamil', 'NotoSansTamil-Regular.ttf')
        if os.path.exists(meipass_font):
            PDF_FONT_FILE = meipass_font
        else:
            # Try other potential locations in the PyInstaller bundle
            for font_name in ['NotoSansTamil-Regular.ttf', 'Lohit-Tamil.ttf']:
                potential_path = os.path.join(BASE_PATH, 'Noto_Sans_Tamil', font_name)
                if os.path.exists(potential_path):
                    PDF_FONT_FILE = potential_path
                    break

_registered_with_reportlab = False
try:
    if PDF_FONT_FILE and os.path.exists(PDF_FONT_FILE):
        # Register TTF with ReportLab
        pdfmetrics.registerFont(TTFont(PDF_FONT_NAME, PDF_FONT_FILE))
        print(f"Successfully registered font: {PDF_FONT_FILE}")  # Debug line
        # Try to register a Bold variant only if a separate bold file exists
        bold_path = None
        if _font_dir and os.path.isdir(_font_dir):
            for f in os.listdir(_font_dir):
                if 'bold' in f.lower() and f.lower().endswith('.ttf'):
                    bold_path = os.path.join(_font_dir, f)
                    break
        if bold_path:
            pdfmetrics.registerFont(TTFont(PDF_FONT_NAME + '-Bold', bold_path))
        _registered_with_reportlab = True
        print(f"✅ Tamil TTF registered for ReportLab PDF: {PDF_FONT_FILE}")
    elif PDF_FONT_FILE and PDF_FONT_FILE.lower().endswith('.otf'):
        # ReportLab may not support OTF shaping fully; rely on WeasyPrint for OTF if available.
        print(f"ℹ️ Found OTF font (will prefer WeasyPrint for shaping): {PDF_FONT_FILE}")
    else:
        print("ℹ️ No TTF/OTF font found for Tamil in project; PDF will use fallback fonts.")
except Exception as e:
    print(f"❌ WARNING: Could not register Tamil TTF ('{PDF_FONT_FILE}') with ReportLab. Error: {e}")
    _registered_with_reportlab = False
    PDF_FONT_NAME = 'Helvetica'
else:
    # Ensure ReportLab doesn't try to use an unregistered font
    if not _registered_with_reportlab:
        PDF_FONT_NAME = 'Helvetica'

# Determine a safe bold font name variable used by ReportLab drawing code.
# If a bold variant was registered use that; otherwise fall back to the base font or Helvetica-Bold.
try:
    if _registered_with_reportlab:
        try:
            pdfmetrics.getFont(PDF_FONT_NAME + '-Bold')
            bold_name = PDF_FONT_NAME + '-Bold'
        except Exception:
            bold_name = PDF_FONT_NAME
    else:
        bold_name = 'Helvetica-Bold'
except Exception:
    bold_name = 'Helvetica-Bold'


# Set up the necessary folders and database tables
def setup_database_and_folders():
    """Initializes the database and creates required tables (Products, Sales, Customers)."""
    os.makedirs('Invoices', exist_ok=True) # Create folder for PDF invoices
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()

    # Table for customizable product names and base prices
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS products (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT UNIQUE NOT NULL,
            rate_per_kg REAL NOT NULL
        )
    ''')
    
    # NEW TABLE: Customer Master
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS customers (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT UNIQUE NOT NULL
        )
    ''')

    # Table for sales history (storing bill summary and line items as JSON)
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS sales_history (
            bill_id INTEGER PRIMARY KEY AUTOINCREMENT,
            transaction_date TEXT NOT NULL,
            customer_name TEXT NOT NULL,
            total_amount REAL NOT NULL,
            items_json TEXT NOT NULL -- Stores list of items as a JSON string
        )
    ''')
    
    # Initialize basic products if the table is empty (User's list)
    initial_products = [
        ('Tomato (தக்காளி)', 25.00), ('Onion (வெங்காயம்)', 35.00), ('Potato (உருளைக்கிழங்கு)', 20.00),
        ('Carrot (கேரட்)', 40.00), ('Brinjal (கத்திரிக்காய்)', 30.00), ('Ladies Finger (வெண்டைக்காய்)', 35.00),
        ('Cabbage (முட்டைக்கோசு)', 28.00), ('Cauliflower (பூக்கோசு)', 32.00), ('Beans (பீன்ஸ்)', 50.00),
        ('Drumstick (முருங்கைக்காய்)', 45.00), ('Cucumber (வெள்ளரிக்காய்)', 25.00), ('Snake Gourd (புடலங்காய்)', 30.00),
        ('Ridge Gourd (பீர்க்கங்காய்)', 35.00), ('Bottle Gourd (சுரைக்காய்)', 28.00), ('Bitter Gourd (பாகற்காய்)', 40.00),
        ('Pumpkin (பூசணிக்காய்)', 25.00), ('Ash Gourd (பூசணிக்காய் வெள்ளை)', 20.00), ('Chow Chow (சௌ சௌ)', 25.00),
        ('Cluster Beans (கொத்தவரங்காய்)', 45.00), ('Broad Beans (அவரைக்காய்)', 45.00), ('Green Peas (பட்டாணி)', 60.00),
        ('Coriander Leaves (கொத்தமல்லி)', 80.00), ('Mint Leaves (புதினா)', 50.00), ('Spinach (பசலைக் கீரை)', 20.00),
        ('Curry Leaves (கருவேப்பிலை)', 100.00), ('Small Onion (சின்ன வெங்காயம்)', 45.00), ('Garlic (பூண்டு)', 130.00),
        ('Ginger (இஞ்சி)', 120.00), ('Green Chilli (பச்சை மிளகாய்)', 70.00), ('Red Chilli (சிவப்பு மிளகாய்)', 150.00),
        ('Beetroot (பீட்ரூட்)', 30.00), ('Radish (முள்ளங்கி)', 25.00), ('Sweet Potato (சக்கரைவள்ளிக்கிழங்கு)', 35.00),
        ('Turnip (நூல்கோசு)', 30.00), ('Yam (சேணைக்கிழங்கு)', 40.00), ('Raw Banana (வாழைக்காய்)', 35.00),
        ('Plantain Stem (வாழைத்தண்டு)', 30.00), ('Plantain Flower (வாழைப்பூ)', 35.00), ('Colocasia (சேப்பங்கிழங்கு)', 45.00),
        ('Turmeric Root (மஞ்சள் வேர்)', 80.00), ('Coconut (தேங்காய்)', 30.00), ('Capsicum (குடைமிளகாய்)', 60.00),
        ('Mushroom (காளான்)', 120.00), ('Spring Onion (வசந்த வெங்காயம்)', 40.00), ('Sweet Corn (இனிப்பு சோளம்)', 45.00),
        ('Ivy Gourd (கோவைக்காய்)', 40.00), ('Avarai Kai (அவரைக்காய்)', 40.00), ('Raw Mango (மாவடைக்காய்)', 50.00),
        ('Tapioca (மரவள்ளிக்கிழங்கு)', 30.00), ('Banana (வாழைப்பழம்)', 45.00), ('Apple (ஆப்பிள்)', 180.00),
        ('Orange (ஆரஞ்சு)', 90.00), ('Mango (மாம்பழம்)', 70.00), ('Papaya (பப்பாளி)', 35.00),
        ('Guava (கொய்யாப்பழம்)', 50.00), ('Pineapple (அன்னாசிப்பழம்)', 60.00), ('Watermelon (தர்பூசணிப்பழம்)', 25.00),
        ('Muskmelon (கீரிப்பழம்)', 40.00), ('Grapes (திராட்சைப்பழம்)', 120.00), ('Pomegranate (மாதுளைப்பழம்)', 160.00),
        ('Sweet Lime (சாத்துக்குடி)', 70.00), ('Lemon (எலுமிச்சை)', 80.00), ('Sapota (சப்போட்டா)', 60.00),
        ('Jackfruit (பலாப்பழம்)', 45.00), ('Custard Apple (சீதாப்பழம்)', 90.00), ('Dates (பேரிச்சம்பழம்)', 180.00),
        ('Fig (அத்திப்பழம்)', 150.00), ('Strawberry (ஸ்ட்ராபெர்ரி)', 250.00), ('Black Grapes (கருப்பு திராட்சை)', 130.00),
        ('Tender Coconut (இளநீர்)', 40.00), ('Wood Apple (விலாம்பழம்)', 35.00), ('Amla (நெல்லிக்காய்)', 60.00),
        ('Rose Apple (ஜம்புலம்)', 70.00), ('Plum (அலுபாலாபழம்)', 120.00), ('Cherry (செர்ரி)', 300.00),
        ('Blueberry (நீலப்பழம்)', 400.00), ('Litchi (லிச்சி)', 150.00), ('Dragon Fruit (பித்தா பழம்)', 180.00),
        ('Pear (பேரிக்காய்)', 120.00), ('Kiwi (கிவி)', 200.00), ('Avocado (வெண்ணெய்ப்பழம்)', 160.00),
        ('Blackberry (கரும்பழம்)', 180.00), ('Coconut (தேங்காய்)', 30.00)
    ]
    initial_customers = [('RAMARAJA BHAVAN',), ('IYARKAI ',),('LITTLE ARABIA',),('HEMA',)]

    for name, rate in initial_products:
        try:
            cursor.execute("INSERT INTO products (name, rate_per_kg) VALUES (?, ?)", (name, rate))
        except sqlite3.IntegrityError:
            pass # Product already exists, skip
            
    for name in initial_customers:
        try:
            cursor.execute("INSERT INTO customers (name) VALUES (?)", name)
        except sqlite3.IntegrityError:
            pass # Customer already exists, skip


    conn.commit()
    conn.close()

# --- UTILITY FUNCTIONS ---

# Function for the unique Kg/Gram display logic
def format_quantity(quantity_kg):
    """Converts a float quantity (e.g., 1.75) into a readable string (1 Kg 750 g)."""
    if not quantity_kg:
        return "0 Kg 0 g"
    
    kg = int(quantity_kg)
    grams = round((quantity_kg - kg) * 1000)
    
    parts = []
    if kg > 0:
        parts.append(f"{kg} Kg")
    if grams > 0:
        parts.append(f"{grams} g")
    
    if not parts:
        return "0 Kg"
        
    return " ".join(parts)

def get_products():
    """Fetches all product data from the database."""
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()
    cursor.execute("SELECT name, rate_per_kg FROM products ORDER BY name")
    products = cursor.fetchall()
    conn.close()
    return products
    
def get_customers():
    """Fetches all customer names from the database."""
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()
    cursor.execute("SELECT name FROM customers ORDER BY name")
    customers = [c[0] for c in cursor.fetchall()]
    conn.close()
    return customers


# --- PDF BILL GENERATION ---

def generate_pdf_invoice(bill_id, customer_name, items, total_amount, title="INVOICE", date_range=None):
    """Generates a professional PDF invoice for the transaction. Added date_range for weekly bill."""
    # If WeasyPrint is available, generate PDF from HTML using @font-face.
    # This produces correct OpenType shaping for Tamil (recommended).
    if WEASY_AVAILABLE:
        try:
            # Resolve font URI for @font-face
            font_path = Path(PDF_FONT_FILE).resolve()
            font_uri = font_path.as_uri()

            # Compose HTML invoice (simple, uses inline styles)
            rows_html = ""
            for it in items:
                if isinstance(it, tuple) and len(it) == 4:
                    name, qty, rate, total = it
                else:
                    name = it['name']
                    qty = it['quantity']
                    rate = it['rate']
                    total = it.get('total', it.get('amount', qty * rate))
                # Split product name into English and Tamil parts if it contains parentheses
                eng_name = name
                tamil_name = ""
                if "(" in name and ")" in name:
                    parts = name.split("(")
                    eng_name = parts[0].strip()
                    tamil_name = "(" + "(".join(parts[1:]).strip()
                
                name_cell = eng_name
                if tamil_name:
                    name_cell += f" <span class='tamil'>{tamil_name}</span>"
                
                rows_html += f"<tr><td>{name_cell}</td><td>{format_quantity(qty)}</td><td style='text-align:right'>{rate:.2f}</td><td style='text-align:right'>{total:.2f}</td></tr>"

            date_display = date_range if date_range else datetime.now().strftime('%d-%b-%Y %H:%M')

            html = f"""
            <html>
            <head>
              <meta charset='utf-8'>
              <style>
                @font-face {{ font-family: 'TamilCustom'; src: url('{font_uri}'); }}
                body {{ font-family: Arial, sans-serif; font-size: 12px; color: #222; }}
                .tamil {{ font-family: 'TamilCustom', sans-serif; }}
                .company {{ font-size: 20px; font-weight: bold; margin-bottom: 6px; }}
                .title {{ font-size: 16px; font-weight: bold; text-align:center; margin: 12px 0; }}
                table {{ width: 100%; border-collapse: collapse; margin-top: 10px; }}
                th, td {{ border: 1px solid #ddd; padding: 6px; }}
                th {{ background: #f5f5f5; text-align: left; }}
                .right {{ text-align: right; }}
                .footer {{ font-size: 10px; text-align:center; margin-top: 18px; color: #666; }}
              </style>
            </head>
            <body>
              <div class='company'>{COMPANY_NAME}</div>
              <div>{COMPANY_ADDRESS} | Phone: {COMPANY_PHONE}</div>
              <div class='title'>{title}</div>
              <div><strong>Bill ID:</strong> {bill_id if bill_id else 'WEEKLY SUMMARY'} &nbsp;&nbsp; <strong>Date:</strong> {date_display}</div>
              <div style='margin-top:6px;'><strong>Billed To:</strong> {customer_name}</div>

              <table>
                <thead>
                  <tr>
                    <th>Product</th>
                    <th>Quantity</th>
                    <th style='text-align:right'>Rate/Kg</th>
                    <th style='text-align:right'>Total</th>
                  </tr>
                </thead>
                <tbody>
                  {rows_html}
                </tbody>
              </table>

              <div style='margin-top:12px; text-align:right; font-weight:bold;'>GRAND TOTAL: ₹{total_amount:.2f}</div>
              <div class='footer'>Thank you for your business. Wholesale transactions only.</div>
            </body>
            </html>
            """

            # Write PDF using WeasyPrint
            # Use customer name + date/time for the filename (safer than Invoice_...)
            filename = make_pdf_filename(customer_name, f"Invoice_{bill_id if bill_id else 'Consolidated'}")
            HTML(string=html).write_pdf(filename)
            return filename
        except Exception as e:
            # If WeasyPrint fails for any reason, log and fall back to ReportLab method below
            print(f"⚠️ WeasyPrint path failed: {e}. Falling back to ReportLab PDF generation.")

    # Fallback: continue with existing ReportLab generation method
    # Use bill_id or 'Consolidated' as fallback; filename uses customer name + date/time
    filename_id = bill_id if bill_id else "Consolidated"
    filename = make_pdf_filename(customer_name, f"Invoice_{filename_id}")
    
    c = canvas.Canvas(filename, pagesize=letter)
    width, height = letter
    
    # Header Area (Company Name) - prefer registered Tamil font (bold) for headings
    try:
        c.setFont(bold_name, 20)
    except Exception:
        try:
            c.setFont(PDF_FONT_NAME if PDF_FONT_NAME != 'Helvetica' else 'Helvetica', 20)
        except Exception:
            c.setFont('Helvetica-Bold', 20)
    c.drawString(1 * inch, height - 1 * inch, COMPANY_NAME)
    
    # Change: Use Tamil font for address if available, otherwise fallback
    c.setFont(PDF_FONT_NAME if PDF_FONT_NAME != 'Helvetica' else 'Helvetica', 10)
    c.drawString(1 * inch, height - 1.25 * inch, COMPANY_ADDRESS)
    c.drawString(1 * inch, height - 1.4 * inch, f"Phone: {COMPANY_PHONE}")
    
    # Title - use Tamil font if available
    try:
        c.setFont(bold_name, 16)
    except Exception:
        try:
            c.setFont(PDF_FONT_NAME if PDF_FONT_NAME != 'Helvetica' else 'Helvetica', 16)
        except Exception:
            c.setFont('Helvetica-Bold', 16)
    c.drawCentredString(width / 2, height - 2 * inch, title)

    # Customer and Invoice Info - headings in bold (prefer Tamil font)
    try:
        c.setFont(bold_name, 12)
    except Exception:
        try:
            c.setFont(PDF_FONT_NAME if PDF_FONT_NAME != 'Helvetica' else 'Helvetica', 12)
        except Exception:
            c.setFont('Helvetica-Bold', 12)
    c.drawString(1 * inch, height - 2.5 * inch, "Bill ID:")
    c.drawString(4 * inch, height - 2.5 * inch, "Date:")
    c.drawString(1 * inch, height - 2.75 * inch, "Billed To:")
    
    # Change: Ensure customer name uses the correct font
    c.setFont(PDF_FONT_NAME if PDF_FONT_NAME != 'Helvetica' else 'Helvetica', 12)
    bill_id_display = str(bill_id) if bill_id else "WEEKLY SUMMARY"
    date_display = date_range if date_range else datetime.now().strftime('%d-%b-%Y %H:%M')
    
    c.drawString(2 * inch, height - 2.5 * inch, bill_id_display)
    c.drawString(5 * inch, height - 2.5 * inch, date_display)
    c.drawString(2 * inch, height - 2.75 * inch, customer_name)
    
    # Table Header (Use Tamil font for Product Name, Quantity, etc., if available)
    y_start = height - 3.5 * inch
    col_x = [1*inch, 3.5*inch, 5.5*inch, 6.5*inch, 7.5*inch]
    
    # FIX: Use registered Tamil font for the table header (for Tamil labels)
    # Try bold variant if registered; otherwise fall back safely to base font
    try:
        c.setFont(bold_name, 11)
    except Exception:
        try:
            c.setFont(PDF_FONT_NAME if PDF_FONT_NAME != 'Helvetica' else 'Helvetica', 11)
        except Exception:
            c.setFont('Helvetica-Bold', 11)
    c.drawString(col_x[0], y_start, "Product Name)")
    c.drawString(col_x[1], y_start, "Quantity")
    c.drawString(col_x[2], y_start, "Rate/Kg")
    c.drawString(col_x[3], y_start, "Total")

    c.setStrokeColor(colors.black)
    c.line(1*inch, y_start - 0.1 * inch, width - 1*inch, y_start - 0.1 * inch) # Horizontal line

    # Item Rows
    # Change: Use Tamil font for item names and quantity format
    c.setFont(PDF_FONT_NAME if PDF_FONT_NAME != 'Helvetica' else 'Helvetica', 11)
    y_pos = y_start - 0.3 * inch
    line_total = 0.0

    for item in items:
        # Item: (name, quantity, rate, total_price)
        # Note: items structure is now (name, quantity, rate, total, [date])
        # For consolidated bill, item is a merged dictionary/tuple
        if isinstance(item, tuple) and len(item) == 4:
            name, quantity, rate, total = item
        else:  # Handle merged item structure for weekly bill
            name, quantity, rate, total = (
                item['name'], item['quantity'], item['rate'], item['total']
            )
            # Optionally display date if needed: c.drawString(1*inch, y_pos, f"  ({item['date']})")
        
        c.drawString(col_x[0], y_pos, name)
        c.drawString(col_x[1], y_pos, format_quantity(quantity))
        c.drawString(col_x[2], y_pos, f"{rate:.2f}")
        c.drawString(col_x[3], y_pos, f"{total:.2f}")
        
        line_total += total
        y_pos -= 0.2 * inch
        
    c.line(1*inch, y_pos - 0.1 * inch, width - 1*inch, y_pos - 0.1 * inch) # Horizontal line

    # Totals Area (English/Numbers)
    y_pos -= 0.3 * inch
    c.setFont('Helvetica-Bold', 12)
    c.drawString(6 * inch, y_pos, "GRAND TOTAL:")
    c.drawString(7.5 * inch, y_pos, f"  {total_amount:.2f}")

    # Footer (English, so keeping Helvetica-Oblique)
    c.setFont('Helvetica-Oblique', 10)
    c.drawCentredString(width / 2, 0.5 * inch, "Thank you for your business. Visit again!")
    c.save()
    return filename

# --- MAIN APPLICATION CLASS ---

class App(ctk.CTk):
    def __init__(self):
        super().__init__()
        # Use COMPANY_NAME (env-backed) to avoid hard-coded personal/company data
        try:
            self.title(f"{COMPANY_NAME} Wholesale Billing System")
        except Exception:
            self.title("Wholesale Billing System")
        # Ensure the window expands fully
        self.geometry("900x600") 
        # Apply unique appearance and use per-widget colors for a custom theme
        ctk.set_appearance_mode("Dark")

        # --- Data Variables ---
        self.current_bill_items = []
        self.current_total = 0.0
        self.customer_var = ctk.StringVar(value="Select Customer or Type Name") # FIX: Changed default text

        # --- Grid Layout (2 columns for sidebar and main content) ---
        # FIX: Ensure row 0 and column 1 take all available space
        self.grid_columnconfigure(1, weight=1)
        self.grid_rowconfigure(0, weight=1)

        # --- Sidebar Frame ---
        self.sidebar_frame = ctk.CTkFrame(self, width=140, corner_radius=0, fg_color=THEME_SIDEBAR)
        # FIX: Removed rowspan=5 and grid_rowconfigure(5, weight=1) to shrink sidebar padding/space
        self.sidebar_frame.grid(row=0, column=0, sticky="nsew")

        # We need to configure grid rows for the buttons to maintain their size,
        # and rely on the default behavior for spacing to be minimal.

        self.logo_label = ctk.CTkLabel(self.sidebar_frame, text=COMPANY_NAME, font=ctk.CTkFont(size=16, weight="bold"), text_color=THEME_TEXT)
        self.logo_label.grid(row=0, column=0, padx=20, pady=(20, 10))

        # Navigation Buttons (Rows 1 through 5)
        # FIX: Added Unicode Emojis for icons
        self.dashboard_button = ctk.CTkButton(self.sidebar_frame, text="Dashboard ", command=self.show_dashboard_screen, fg_color=THEME_ACCENT, hover_color=THEME_ACCENT_HOVER, text_color=THEME_SIDEBAR)
        self.dashboard_button.grid(row=1, column=0, padx=20, pady=10)

        self.billing_button = ctk.CTkButton(self.sidebar_frame, text="New Bill", command=self.show_billing_screen, fg_color=THEME_ACCENT, hover_color=THEME_ACCENT_HOVER, text_color=THEME_SIDEBAR)
        self.billing_button.grid(row=2, column=0, padx=20, pady=10)

        self.customers_button = ctk.CTkButton(self.sidebar_frame, text="Customer Master", command=self.show_customer_master, fg_color=THEME_ACCENT, hover_color=THEME_ACCENT_HOVER, text_color=THEME_SIDEBAR)
        self.customers_button.grid(row=3, column=0, padx=20, pady=10)

        self.products_button = ctk.CTkButton(self.sidebar_frame, text="Product Master", command=self.show_product_screen, fg_color=THEME_ACCENT, hover_color=THEME_ACCENT_HOVER, text_color=THEME_SIDEBAR)
        self.products_button.grid(row=4, column=0, padx=20, pady=10)

        # FIX: The space issue comes from row 5 having weight=1.
        # We set row 6 (the row after the last button) to take up all remaining space.
        self.history_button = ctk.CTkButton(self.sidebar_frame, text="Bill History", command=self.show_history_screen, fg_color=THEME_ACCENT, hover_color=THEME_ACCENT_HOVER, text_color=THEME_SIDEBAR)
        self.history_button.grid(row=5, column=0, padx=20, pady=10)

        # Set the row AFTER the last button (row 6) to take up all vertical space.
        self.sidebar_frame.grid_rowconfigure(6, weight=1)


        # --- Main Content Frame ---
        self.main_frame = ctk.CTkFrame(self, fg_color=THEME_MAIN)
        self.main_frame.grid(row=0, column=1, sticky="nsew", padx=10, pady=10)
        # FIX: Main frame must be configured to expand
        self.main_frame.grid_columnconfigure(0, weight=1)
        self.main_frame.grid_rowconfigure(0, weight=1)

        # Initialize screens
        self.dashboard_frame = None # NEW
        self.billing_frame = None
        self.customer_frame = None # NEW
        self.product_frame = None
        self.history_frame = None

        # Show the default screen
        self.show_dashboard_screen()


    # --- Screen Management ---

    def hide_frames(self):
        """Hides all non-sidebar frames."""
        for frame in [self.dashboard_frame, self.billing_frame, self.customer_frame, self.product_frame, self.history_frame]:
            if frame:
                frame.grid_forget()
                
    def show_dashboard_screen(self):
        self.hide_frames()
        if self.dashboard_frame is None:
            self.dashboard_frame = DashboardScreen(self.main_frame, self)
        self.dashboard_frame.grid(row=0, column=0, sticky="nsew", padx=5, pady=5)
        self.dashboard_frame.grid_columnconfigure(0, weight=1)
        self.dashboard_frame.grid_rowconfigure(0, weight=1)
        self.dashboard_frame.load_report_data() # Load data when switching to this screen


    def show_billing_screen(self):
        self.hide_frames()
        if self.billing_frame is None:
            self.billing_frame = BillingScreen(self.main_frame, self)
        # FIX: Ensure it expands to fill the main_frame
        self.billing_frame.grid(row=0, column=0, sticky="nsew", padx=5, pady=5) 
        self.billing_frame.grid_columnconfigure(0, weight=1)
        self.billing_frame.grid_rowconfigure(1, weight=1)
        self.billing_frame.load_customer_options() # FIX: Load customer options
        self.billing_frame.load_product_options()
        self.billing_frame.update_bill_summary()
        

    def show_customer_master(self):
        self.hide_frames()
        if self.customer_frame is None:
            self.customer_frame = CustomerMasterScreen(self.main_frame, self)
        self.customer_frame.grid(row=0, column=0, sticky="nsew", padx=5, pady=5)
        self.customer_frame.grid_columnconfigure(0, weight=1)
        self.customer_frame.grid_rowconfigure(1, weight=1)
        self.customer_frame.load_customers_to_view()

    def show_product_screen(self):
        self.hide_frames()
        if self.product_frame is None:
            self.product_frame = ProductMasterScreen(self.main_frame, self)
        # FIX: Ensure it expands to fill the main_frame
        self.product_frame.grid(row=0, column=0, sticky="nsew", padx=5, pady=5)
        self.product_frame.grid_columnconfigure(0, weight=1)
        self.product_frame.grid_rowconfigure(1, weight=1)
        self.product_frame.load_products_to_view()

    def show_history_screen(self):
        self.hide_frames()
        if self.history_frame is None:
            self.history_frame = HistoryScreen(self.main_frame, self)
        # FIX: Ensure it expands to fill the main_frame
        self.history_frame.grid(row=0, column=0, sticky="nsew", padx=5, pady=5)
        self.history_frame.grid_columnconfigure(0, weight=1)
        self.history_frame.grid_rowconfigure(1, weight=1)
        self.history_frame.load_sales_history()


# --- DASHBOARD SCREEN CLASS (NEW) ---

class DashboardScreen(ctk.CTkFrame):
    def __init__(self, master, app_instance):
        super().__init__(master)
        self.app = app_instance
        self.grid_columnconfigure((0, 1, 2), weight=1)
        self.grid_rowconfigure(1, weight=1)

        ctk.CTkLabel(self, text="Sales Dashboard (விற்பனை அறிக்கை)", font=ctk.CTkFont(size=20, weight="bold")).grid(row=0, column=0, columnspan=3, padx=10, pady=(10, 20), sticky="w")
        
        # Data storage for the summary boxes
        self.summary_labels = {}
        
        # Create summary boxes
        timeframes = [("Today", "இன்று"), ("This Week", "இந்த வாரம்"), ("This Month", "இந்த மாதம்")]
        
        for i, (tf_en, tf_ta) in enumerate(timeframes):
            # FIX: Changed fg_color to transparent and removed corner_radius for the look seen in the image
            frame = ctk.CTkFrame(self, fg_color="transparent", corner_radius=0) 
            frame.grid(row=1, column=i, padx=15, pady=15, sticky="nsew")
            frame.grid_columnconfigure(0, weight=1)
            
            ctk.CTkLabel(frame, text=f"{tf_ta} ({tf_en})", font=ctk.CTkFont(size=16, weight="bold"), text_color="gray50").grid(row=0, column=0, padx=20, pady=10, sticky="w")
            
            # Amount Label
            amount_label = ctk.CTkLabel(frame, text="₹0.00", font=ctk.CTkFont(size=28, weight="bold"), text_color="green")
            amount_label.grid(row=1, column=0, padx=20, pady=5, sticky="w")
            self.summary_labels[f'{tf_en}_amount'] = amount_label
            
            # Count Label
            count_label = ctk.CTkLabel(frame, text="0 Bills", font=ctk.CTkFont(size=14), text_color="gray")
            count_label.grid(row=2, column=0, padx=20, pady=(0, 10), sticky="w")
            self.summary_labels[f'{tf_en}_count'] = count_label

    def load_report_data(self):
        """Calculates and updates the sales summary data for various timeframes."""
        conn = sqlite3.connect(DB_NAME)
        cursor = conn.cursor()
        
        now = datetime.now()
        
        # Today's data
        today_start = now.replace(hour=0, minute=0, second=0, microsecond=0).strftime('%Y-%m-%d %H:%M:%S')
        
        # Week's data (Start of week is Monday)
        week_start = (now - timedelta(days=now.weekday())).replace(hour=0, minute=0, second=0, microsecond=0).strftime('%Y-%m-%d %H:%M:%S')
        
        # Month's data
        month_start = now.replace(day=1, hour=0, minute=0, second=0, microsecond=0).strftime('%Y-%m-%d %H:%M:%S')
        
        timeframes = [
            ('Today', today_start),
            ('This Week', week_start),
            ('This Month', month_start)
        ]

        for tf_en, start_date in timeframes:
            query = f"""
                SELECT SUM(total_amount), COUNT(bill_id) 
                FROM sales_history 
                WHERE transaction_date >= '{start_date}'
            """
            cursor.execute(query)
            result = cursor.fetchone()
            
            total_amount = result[0] if result and result[0] is not None else 0.0
            bill_count = result[1] if result and result[1] is not None else 0
            
            self.summary_labels[f'{tf_en}_amount'].configure(text=f"₹{total_amount:,.2f}")
            self.summary_labels[f'{tf_en}_count'].configure(text=f"{bill_count} Bills")
            
        conn.close()


# --- BILLING SCREEN CLASS ---

class BillingScreen(ctk.CTkFrame):
    def __init__(self, master, app_instance):
        super().__init__(master)
        self.app = app_instance
        
        self.grid_columnconfigure(0, weight=1)
        self.grid_rowconfigure(1, weight=1)
        
        self.customer_options = get_customers() # Initial load of customer list
        
        # Store bill_id being edited, if any
        self.editing_bill_id = None 

        # Top Bar for Customer Input
        customer_frame = ctk.CTkFrame(self)
        customer_frame.grid(row=0, column=0, padx=10, pady=(10, 5), sticky="ew")
        customer_frame.grid_columnconfigure((1, 2), weight=1)
        customer_frame.grid_columnconfigure(0, weight=0)

        ctk.CTkLabel(customer_frame, text="Customer Name:", font=ctk.CTkFont(weight="bold")).grid(row=0, column=0, padx=10, pady=10, sticky="w")
        
        # NEW: Dropdown for existing customers
        self.customer_dropdown = ctk.CTkOptionMenu(customer_frame, variable=self.app.customer_var, values=self.customer_options, command=self.update_customer_entry, width=200)
        self.customer_dropdown.grid(row=0, column=1, padx=10, pady=10, sticky="ew")
        
        # Entry for typing custom customer name
        self.customer_entry = ctk.CTkEntry(customer_frame, textvariable=self.app.customer_var, width=400)
        self.customer_entry.grid(row=0, column=2, padx=10, pady=10, sticky="ew")


        # Line Item Entry Frame
        item_frame = ctk.CTkFrame(self)
        item_frame.grid(row=1, column=0, padx=10, pady=5, sticky="nsew")
        # FIX: Adjusted weights to give Rate/Kg column less space
        item_frame.grid_columnconfigure(0, weight=4) # Item Name (Dropdown)
        item_frame.grid_columnconfigure(1, weight=1) # Rate/Kg (Editable)
        item_frame.grid_columnconfigure(2, weight=2) # Quantity (Kg)
        item_frame.grid_columnconfigure(3, weight=1) # Total
        item_frame.grid_columnconfigure(4, weight=1) # Add Button

        # Labels
        ctk.CTkLabel(item_frame, text="Item Name", font=ctk.CTkFont(weight="bold")).grid(row=0, column=0, padx=5, pady=5)
        ctk.CTkLabel(item_frame, text="Rate/Kg (₹)", font=ctk.CTkFont(weight="bold")).grid(row=0, column=1, padx=5, pady=5)
        ctk.CTkLabel(item_frame, text="Quantity (Kg)", font=ctk.CTkFont(weight="bold")).grid(row=0, column=2, padx=5, pady=5)
        ctk.CTkLabel(item_frame, text="Total (₹)", font=ctk.CTkFont(weight="bold")).grid(row=0, column=3, padx=5, pady=5)
        ctk.CTkLabel(item_frame, text="Action", font=ctk.CTkFont(weight="bold")).grid(row=0, column=4, padx=5, pady=5)
        
        # Inputs
        self.product_options = []
        self.selected_product = tk.StringVar()
        self.rate_var = ctk.StringVar(value="0.00") # FIX: Variable to hold editable rate

        # Use a ttk.Combobox for product selection (allows typing + dropdown, more comfortable than spin buttons)
        self.item_dropdown = ttk.Combobox(item_frame, textvariable=self.selected_product, values=self.product_options)
        self.item_dropdown.state(['!readonly'])  # allow typing
        self.item_dropdown.grid(row=1, column=0, padx=5, pady=5, sticky="ew")
        # Bind selection and typing events to update rate
        self.item_dropdown.bind('<<ComboboxSelected>>', lambda e: self.update_rate(self.selected_product.get()))
        self.item_dropdown.bind('<FocusOut>', lambda e: self.update_rate(self.selected_product.get()))
        self.item_dropdown.bind('<KeyRelease>', lambda e: None)
        
        # FIX: Changed rate_label to an editable CTkEntry
        self.rate_entry = ctk.CTkEntry(item_frame, textvariable=self.rate_var)
        self.rate_entry.grid(row=1, column=1, padx=5, pady=5, sticky="ew")
        self.rate_entry.bind("<KeyRelease>", self.calculate_total_price)
        
        self.quantity_entry = ctk.CTkEntry(item_frame, placeholder_text="e.g., 1.75 for 1kg 750g")
        self.quantity_entry.grid(row=1, column=2, padx=5, pady=5, sticky="ew")
        self.quantity_entry.bind("<KeyRelease>", self.calculate_total_price)
        
        self.line_total_label = ctk.CTkLabel(item_frame, text="0.00", text_color="cyan")
        self.line_total_label.grid(row=1, column=3, padx=5, pady=5, sticky="ew")
        
        self.add_button = ctk.CTkButton(item_frame, text="Add Item", command=self.add_item_to_bill)
        self.add_button.grid(row=1, column=4, padx=5, pady=5)

        # Bill Display Area
        ctk.CTkLabel(self, text="Current Bill Items", font=ctk.CTkFont(size=14, weight="bold")).grid(row=2, column=0, padx=10, pady=(10, 0), sticky="w")
        
        self.bill_display_frame = ctk.CTkScrollableFrame(self, label_text="Itemized List")
        self.bill_display_frame.grid(row=3, column=0, padx=10, pady=5, sticky="nsew")
        self.bill_display_frame.grid_columnconfigure(0, weight=1)

        # Summary and Finalization
        summary_frame = ctk.CTkFrame(self)
        summary_frame.grid(row=4, column=0, padx=10, pady=(5, 10), sticky="ew")
        summary_frame.grid_columnconfigure(0, weight=1)
        summary_frame.grid_columnconfigure(1, weight=1)
        
        ctk.CTkLabel(summary_frame, text="GRAND TOTAL:").grid(row=0, column=0, padx=10, pady=10, sticky="e")
        self.total_label = ctk.CTkLabel(summary_frame, text="₹0.00", font=ctk.CTkFont(size=20, weight="bold"), text_color="lightgreen")
        self.total_label.grid(row=0, column=1, padx=(0, 20), pady=10, sticky="w")
        
        # Finalization Buttons
        self.weekly_save_button = ctk.CTkButton(summary_frame, text="Save for Weekly Bill (No Print)", command=lambda: self.finalize_bill(print_immediately=False))
        self.weekly_save_button.grid(row=1, column=0, padx=10, pady=10, sticky="ew")
        
        self.finalize_button = ctk.CTkButton(summary_frame, text="FINALIZE & PRINT BILL (PDF)", command=lambda: self.finalize_bill(print_immediately=True), fg_color="green", hover_color="#006400")
        self.finalize_button.grid(row=1, column=1, padx=10, pady=10, sticky="ew")
        
    def update_customer_entry(self, choice):
        """Updates the entry field when a customer is selected from the dropdown."""
        self.app.customer_var.set(choice)
        
    def load_customer_options(self):
        """Loads customers from DB into the dropdown menu."""
        customers = get_customers()
        self.customer_dropdown.configure(values=customers)
        
        # Attempt to set default selection
        if customers:
            if self.app.customer_var.get() not in customers:
                self.app.customer_var.set(customers[0])
        else:
            self.app.customer_var.set("Type Customer Name")
        
    def load_product_options(self):
        """Loads products from DB into the dropdown menu."""
        products = get_products()
        self.product_options = [p[0] for p in products]
        if self.product_options:
            self.item_dropdown.configure(values=self.product_options)
            self.selected_product.set(self.product_options[0])
            self.update_rate(self.selected_product.get())

    def get_rate(self, item_name):
        """Retrieves the rate per kg for a given item name."""
        conn = sqlite3.connect(DB_NAME)
        cursor = conn.cursor()
        cursor.execute("SELECT rate_per_kg FROM products WHERE name = ?", (item_name,))
        rate = cursor.fetchone()
        conn.close()
        return rate[0] if rate else 0.0

    def update_rate(self, item_name):
        """Updates the rate display when a product is selected."""
        rate = self.get_rate(item_name)
        # FIX: Update the editable entry field
        self.rate_var.set(f"{rate:.2f}") 
        self.calculate_total_price(None) # Recalculate line total

    def calculate_total_price(self, event):
        """Calculates and updates the line total based on quantity and rate."""
        try:
            # FIX: Get rate from the editable entry field
            rate = float(self.rate_var.get())
            quantity = float(self.quantity_entry.get())
            total = rate * quantity
            self.line_total_label.configure(text=f"{total:.2f}")
        except ValueError:
            self.line_total_label.configure(text="0.00")
            
    def add_item_to_bill(self):
        """Adds the current item entry to the bill list."""
        item_name = self.selected_product.get()
        try:
            # FIX: Get rate from the editable entry field
            rate = float(self.rate_var.get())
            quantity = float(self.quantity_entry.get())
        except ValueError:
            messagebox.showerror("Input Error", "Please enter valid Rate and Quantity (numbers).")
            return
            
        if quantity <= 0:
            messagebox.showerror("Input Error", "Quantity must be greater than zero.")
            return

        total_price = quantity * rate
        
        # Bill Item Format: (name, quantity_kg, rate_per_kg, total_price)
        new_item = (item_name, quantity, rate, total_price)
        self.app.current_bill_items.append(new_item)
        self.app.current_total += total_price
        
        self.quantity_entry.delete(0, 'end')
        self.update_bill_summary()
        
        # Clear editing state if an item is added
        self.editing_bill_id = None
        self.finalize_button.configure(text="FINALIZE & PRINT BILL (PDF)")


    def load_bill_for_edit(self, bill_data):
        """Loads items from a historical bill into the current bill for editing."""
        bill_id, customer, items_json, total_amount = bill_data
        items = json.loads(items_json)
        
        # Clear current bill and reset variables
        self.app.current_bill_items = []
        self.app.current_total = 0.0
        
        # Set editing state
        self.editing_bill_id = bill_id
        self.app.customer_var.set(customer)
        self.finalize_button.configure(text=f"UPDATE BILL {bill_id} & PRINT")
        
        # Load items
        for item in items:
            name, quantity, rate, total = item
            # Item: (name, quantity_kg, rate_per_kg, total_price)
            self.app.current_bill_items.append((name, quantity, rate, total))
            self.app.current_total += total
            
        self.update_bill_summary()
        self.app.show_billing_screen() # Switch to billing screen
        
    def update_bill_summary(self):
        """Refreshes the displayed list of items and the grand total."""
        # Clear previous items
        for widget in self.bill_display_frame.winfo_children():
            widget.destroy()
        
        for i, item in enumerate(self.app.current_bill_items):
            name, quantity, rate, total = item
            
            # Use format_quantity for the unique display
            quantity_display = format_quantity(quantity)
            
            # Row Frame
            row_frame = ctk.CTkFrame(self.bill_display_frame, fg_color="transparent")
            row_frame.grid(row=i, column=0, padx=5, pady=2, sticky="ew")
            row_frame.grid_columnconfigure(0, weight=4) # Name
            row_frame.grid_columnconfigure(1, weight=2) # Quantity
            row_frame.grid_columnconfigure(2, weight=1) # Rate
            row_frame.grid_columnconfigure(3, weight=1) # Total
            row_frame.grid_columnconfigure(4, weight=1) # Remove Button
            
            ctk.CTkLabel(row_frame, text=name, anchor="w").grid(row=0, column=0, padx=5, sticky="w")
            ctk.CTkLabel(row_frame, text=quantity_display, anchor="w").grid(row=0, column=1, padx=5, sticky="w")
            ctk.CTkLabel(row_frame, text=f"@{rate:.2f}", anchor="w").grid(row=0, column=2, padx=5, sticky="w")
            ctk.CTkLabel(row_frame, text=f"₹{total:.2f}", anchor="e", font=ctk.CTkFont(weight="bold")).grid(row=0, column=3, padx=5, sticky="e")
            
            remove_btn = ctk.CTkButton(row_frame, text="X", width=30, fg_color="red", hover_color="#8B0000", command=lambda idx=i: self.remove_item(idx))
            remove_btn.grid(row=0, column=4, padx=5, sticky="e")
            
        self.total_label.configure(text=f"₹{self.app.current_total:.2f}")
        
        # Update button text based on editing state
        if self.editing_bill_id:
            self.finalize_button.configure(text=f"UPDATE BILL {self.editing_bill_id} & PRINT")
        else:
            self.finalize_button.configure(text="FINALIZE & PRINT BILL (PDF)")


    def remove_item(self, index):
        """Removes an item from the current bill list."""
        removed_item = self.app.current_bill_items.pop(index)
        self.app.current_total -= removed_item[3] # Subtract total price
        self.update_bill_summary()

    def finalize_bill(self, print_immediately=True):
        """Saves the bill to the database and generates the PDF."""
        customer = self.app.customer_var.get().strip()
        
        # Handle editing vs new bill
        bill_id_to_save = self.editing_bill_id
        
        if customer == "Select Customer or Type Name" or not customer:
            messagebox.showerror("Error", "Please enter a valid Customer Name.")
            return

        if not self.app.current_bill_items:
            messagebox.showerror("Error", "Bill is empty. Please add items.")
            return

        conn = sqlite3.connect(DB_NAME)
        cursor = conn.cursor()
        
        # 1. Save customer name to master list if new
        try:
            cursor.execute("INSERT INTO customers (name) VALUES (?)", (customer,))
            conn.commit()
            if self.app.customer_frame:
                self.app.customer_frame.load_customers_to_view()
        except sqlite3.IntegrityError:
            pass # Customer already exists
        
        # 2. Save/Update to sales_history
        items_json = json.dumps(self.app.current_bill_items)
        total_amount = self.app.current_total
        current_datetime = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
        
        try:
            if bill_id_to_save:
                # Update existing bill
                cursor.execute('''
                    UPDATE sales_history SET transaction_date=?, customer_name=?, total_amount=?, items_json=?
                    WHERE bill_id=?
                ''', (current_datetime, customer, total_amount, items_json, bill_id_to_save))
                conn.commit()
                message_action = f"Bill (ID: {bill_id_to_save}) updated"
                last_bill_id = bill_id_to_save
            else:
                # Insert new bill
                cursor.execute('''
                    INSERT INTO sales_history (transaction_date, customer_name, total_amount, items_json)
                    VALUES (?, ?, ?, ?)
                ''', (current_datetime, customer, total_amount, items_json))
                conn.commit()
                last_bill_id = cursor.lastrowid
                message_action = f"Bill (ID: {last_bill_id}) saved"
            
            conn.close()
            
            # 3. Generate PDF if required
            if print_immediately:
                pdf_path = generate_pdf_invoice(last_bill_id, customer, self.app.current_bill_items, total_amount)
                messagebox.showinfo("Success", f"{message_action} and PDF generated at:\n{pdf_path}")
            else:
                messagebox.showinfo("Saved", f"{message_action} successfully for weekly billing.")
                
            # 4. Reset state
            self.editing_bill_id = None
            self.app.current_bill_items = []
            self.app.current_total = 0.0
            self.app.customer_var.set("Select Customer or Type Name")
            self.update_bill_summary()
            
            # 5. Update other screens
            if self.app.dashboard_frame:
                self.app.dashboard_frame.load_report_data()
            if self.app.history_frame:
                self.app.history_frame.load_sales_history()

        except sqlite3.Error as e:
            messagebox.showerror("Database Error", f"Failed to save/update bill: {e}")
            conn.close()

# --- CUSTOMER MASTER SCREEN CLASS (NEW) ---

class CustomerMasterScreen(ctk.CTkFrame):
    def __init__(self, master, app_instance):
        super().__init__(master)
        self.app = app_instance
        self.grid_columnconfigure(0, weight=1)
        self.grid_rowconfigure(1, weight=1)

        ctk.CTkLabel(self, text="Customer Master (வாடிக்கையாளர் விவரங்கள்)", font=ctk.CTkFont(size=18, weight="bold")).grid(row=0, column=0, padx=10, pady=(10, 5), sticky="w")
        
        # Customer Entry Frame
        entry_frame = ctk.CTkFrame(self)
        entry_frame.grid(row=0, column=0, padx=10, pady=5, sticky="ew")
        entry_frame.grid_columnconfigure(1, weight=1)

        ctk.CTkLabel(entry_frame, text="Customer Name:").grid(row=0, column=0, padx=5, pady=5)
        self.name_entry = ctk.CTkEntry(entry_frame)
        self.name_entry.grid(row=0, column=1, padx=5, pady=5, sticky="ew")
        
        self.action_button = ctk.CTkButton(entry_frame, text="Add/Update Customer", command=self.add_or_update_customer)
        self.action_button.grid(row=0, column=2, padx=10, pady=5)
        
        # Customer List Display
        self.customer_list_frame = ctk.CTkScrollableFrame(self, label_text="Existing Customers")
        self.customer_list_frame.grid(row=1, column=0, padx=10, pady=5, sticky="nsew")
        self.customer_list_frame.grid_columnconfigure(0, weight=1)

        self.load_customers_to_view()


    def load_customers_to_view(self):
        """Fetches and displays all customers in the Customer Master tab."""
        for widget in self.customer_list_frame.winfo_children():
            widget.destroy()

        customers = get_customers()
        
        # Header Row
        header_frame = ctk.CTkFrame(self.customer_list_frame, fg_color="transparent")
        header_frame.grid(row=0, column=0, padx=5, pady=2, sticky="ew")
        
        header_frame.grid_columnconfigure(0, weight=5) # Name
        header_frame.grid_columnconfigure(1, weight=0) # Edit Button container
        header_frame.grid_columnconfigure(2, weight=0) # Delete Button container
        
        ctk.CTkLabel(header_frame, text="CUSTOMER NAME", font=ctk.CTkFont(weight="bold")).grid(row=0, column=0, padx=5, sticky="w")


        for i, name in enumerate(customers):
            row_frame = ctk.CTkFrame(self.customer_list_frame, fg_color="transparent")
            row_frame.grid(row=i + 1, column=0, padx=5, pady=2, sticky="ew")
            
            row_frame.grid_columnconfigure(0, weight=5)
            row_frame.grid_columnconfigure(1, weight=0)
            row_frame.grid_columnconfigure(2, weight=0)

            ctk.CTkLabel(row_frame, text=name, anchor="w").grid(row=0, column=0, padx=5, sticky="w")
            
            # Edit Button
            edit_btn = ctk.CTkButton(row_frame, text="Edit", width=60, command=lambda n=name: self.prefill_for_edit(n))
            edit_btn.grid(row=0, column=1, padx=5, sticky="e")
            
            # Delete Button
            delete_btn = ctk.CTkButton(row_frame, text="Delete", width=60, fg_color="red", hover_color="#8B0000", command=lambda n=name: self.delete_customer(n))
            delete_btn.grid(row=0, column=2, padx=5, sticky="e")

    def prefill_for_edit(self, name):
        """Fills the entry fields with selected customer data for editing."""
        self.name_entry.delete(0, 'end')
        self.name_entry.insert(0, name)
        self.action_button.configure(text="Update Customer")
        
    def add_or_update_customer(self):
        """Adds a new customer or updates an existing one."""
        name = self.name_entry.get().strip()
        
        if not name:
            messagebox.showerror("Input Error", "Customer Name cannot be empty.")
            return

        conn = sqlite3.connect(DB_NAME)
        cursor = conn.cursor()
        
        # Use INSERT OR REPLACE to update if the name already exists
        try:
            cursor.execute('''
                INSERT OR REPLACE INTO customers (name) 
                VALUES (?)
            ''', (name,))
            conn.commit()
            
            messagebox.showinfo("Success", f"Customer '{name}' updated/added successfully.")
            self.name_entry.delete(0, 'end')
            self.action_button.configure(text="Add/Update Customer")
            self.load_customers_to_view()
            if self.app.billing_frame:
                self.app.billing_frame.load_customer_options() # Refresh options in billing tab
                
        except sqlite3.Error as e:
            messagebox.showerror("Database Error", f"Failed to save customer: {e}")
        finally:
            conn.close()

    def delete_customer(self, name):
        """Deletes a customer after confirmation."""
        if messagebox.askyesno("Confirm Delete", f"Are you sure you want to permanently delete customer '{name}'? This cannot be undone."):
            conn = sqlite3.connect(DB_NAME)
            cursor = conn.cursor()
            
            try:
                cursor.execute("DELETE FROM customers WHERE name = ?", (name,))
                conn.commit()
                messagebox.showinfo("Deleted", f"Customer '{name}' has been successfully deleted.")
                
                self.load_customers_to_view() # Refresh the list view
                if self.app.billing_frame:
                    self.app.billing_frame.load_customer_options() # Refresh options in billing tab
                    
            except sqlite3.Error as e:
                messagebox.showerror("Database Error", f"Failed to delete customer: {e}")
            finally:
                conn.close()


# --- PRODUCT MASTER SCREEN CLASS ---

class ProductMasterScreen(ctk.CTkFrame):
    def __init__(self, master, app_instance):
        super().__init__(master)
        self.app = app_instance
        self.grid_columnconfigure(0, weight=1)
        self.grid_rowconfigure(1, weight=1)

        ctk.CTkLabel(self, text="Product Master (விலை & அலகு மாற்றம்)", font=ctk.CTkFont(size=18, weight="bold")).grid(row=0, column=0, padx=10, pady=(10, 5), sticky="w")
        
        # Product Entry Frame
        entry_frame = ctk.CTkFrame(self)
        entry_frame.grid(row=0, column=0, padx=10, pady=5, sticky="ew")
        entry_frame.grid_columnconfigure((1, 3, 5), weight=1)

        ctk.CTkLabel(entry_frame, text="Name:").grid(row=0, column=0, padx=5, pady=5)
        self.name_entry = ctk.CTkEntry(entry_frame)
        self.name_entry.grid(row=0, column=1, padx=5, pady=5, sticky="ew")
        
        ctk.CTkLabel(entry_frame, text="Rate/Kg (₹):").grid(row=0, column=2, padx=5, pady=5)
        self.rate_entry = ctk.CTkEntry(entry_frame)
        self.rate_entry.grid(row=0, column=3, padx=5, pady=5, sticky="ew")
        
        self.add_product_button = ctk.CTkButton(entry_frame, text="Add/Update Product", command=self.add_or_update_product)
        self.add_product_button.grid(row=0, column=4, padx=10, pady=5)
        
        # Product List Display
        self.product_list_frame = ctk.CTkScrollableFrame(self, label_text="Existing Products")
        self.product_list_frame.grid(row=1, column=0, padx=10, pady=5, sticky="nsew")
        self.product_list_frame.grid_columnconfigure(0, weight=1)

        self.load_products_to_view()


    def load_products_to_view(self):
        """Fetches and displays all products in the Product Master tab."""
        for widget in self.product_list_frame.winfo_children():
            widget.destroy()

        products = get_products()
        
        # Header Row
        header_frame = ctk.CTkFrame(self.product_list_frame, fg_color="transparent")
        header_frame.grid(row=0, column=0, padx=5, pady=2, sticky="ew")
        
        # FIX: Adjusted weights for better alignment in Product Master Header (Rate takes up minimal fixed space)
        header_frame.grid_columnconfigure(0, weight=4) # Name - More space
        header_frame.grid_columnconfigure(1, weight=1) # Rate - Fixed space
        header_frame.grid_columnconfigure(2, weight=0) # Edit Button container
        header_frame.grid_columnconfigure(3, weight=0) # Delete Button container
        
        ctk.CTkLabel(header_frame, text="PRODUCT NAME", font=ctk.CTkFont(weight="bold")).grid(row=0, column=0, padx=5, sticky="w")
        ctk.CTkLabel(header_frame, text="RATE/KG (₹)", font=ctk.CTkFont(weight="bold")).grid(row=0, column=1, padx=5, sticky="w")


        for i, product in enumerate(products):
            # product is (name, rate_per_kg)
            try:
                pname, prate = product
            except Exception:
                # defensive fallback if schema changes
                pname = str(product)
                prate = 0.0

            row_frame = ctk.CTkFrame(self.product_list_frame, fg_color="transparent")
            row_frame.grid(row=i + 1, column=0, padx=5, pady=2, sticky="ew")

            # Adjusted weights for better alignment in Product Master Rows
            row_frame.grid_columnconfigure(0, weight=4)
            row_frame.grid_columnconfigure(1, weight=1)
            row_frame.grid_columnconfigure(2, weight=0) # Edit button
            row_frame.grid_columnconfigure(3, weight=0) # Delete button

            ctk.CTkLabel(row_frame, text=pname, anchor="w").grid(row=0, column=0, padx=5, sticky="w")
            # Align the rate to the left for consistency
            ctk.CTkLabel(row_frame, text=f"₹{prate:.2f}", anchor="w").grid(row=0, column=1, padx=5, sticky="w") 

            # Edit Button
            edit_btn = ctk.CTkButton(row_frame, text="Edit", width=60, command=lambda n=pname, r=prate: self.prefill_for_edit(n, r))
            edit_btn.grid(row=0, column=2, padx=5, sticky="e")

            # Delete Button
            delete_btn = ctk.CTkButton(row_frame, text="Delete", width=60, fg_color="red", hover_color="#8B0000", command=lambda n=pname: self.delete_product(n))
            delete_btn.grid(row=0, column=3, padx=5, sticky="e") # Placed next to Edit

    def prefill_for_edit(self, name, rate):
        """Fills the entry fields with selected product data for editing."""
        self.name_entry.delete(0, 'end')
        self.name_entry.insert(0, name)
        self.rate_entry.delete(0, 'end')
        self.rate_entry.insert(0, str(rate))
        
    def add_or_update_product(self):
        """Adds a new product or updates an existing one."""
        name = self.name_entry.get().strip()
        try:
            rate = float(self.rate_entry.get())
        except ValueError:
            messagebox.showerror("Input Error", "Rate must be a valid number.")
            return

        if not name:
            messagebox.showerror("Input Error", "Product Name cannot be empty.")
            return

        conn = sqlite3.connect(DB_NAME)
        cursor = conn.cursor()
        
        # Use INSERT OR REPLACE to update if the name already exists
        # NOTE: name is UNIQUE in the table definition
        try:
            cursor.execute('''
                INSERT OR REPLACE INTO products (name, rate_per_kg) 
                VALUES (?, ?)
            ''', (name, rate))
            conn.commit()
            
            messagebox.showinfo("Success", f"Product '{name}' updated/added successfully.")
            self.name_entry.delete(0, 'end')
            self.rate_entry.delete(0, 'end')
            self.load_products_to_view()
            if self.app.billing_frame:
                self.app.billing_frame.load_product_options() # Refresh options in billing tab
                
        except sqlite3.Error as e:
            messagebox.showerror("Database Error", f"Failed to save product: {e}")
        finally:
            conn.close()

    def delete_product(self, name):
        """Deletes a product after confirmation."""
        # Use a custom dialog or a standard messagebox.askyesno for confirmation
        # Since tkinter's messagebox is used elsewhere, we stick to it for consistency
        
        if messagebox.askyesno("Confirm Delete", f"Are you sure you want to permanently delete '{name}'? This cannot be undone."):
            conn = sqlite3.connect(DB_NAME)
            cursor = conn.cursor()
            
            try:
                # Delete the product based on its unique name
                cursor.execute("DELETE FROM products WHERE name = ?", (name,))
                conn.commit()
                messagebox.showinfo("Deleted", f"Product '{name}' has been successfully deleted.")
                
                self.load_products_to_view() # Refresh the list view
                if self.app.billing_frame:
                    self.app.billing_frame.load_product_options() # Refresh options in billing tab
                    
            except sqlite3.Error as e:
                messagebox.showerror("Database Error", f"Failed to delete product: {e}")
            finally:
                conn.close()


# --- HISTORY SCREEN CLASS ---

class HistoryScreen(ctk.CTkFrame):
    # Class-level variable to store the last deleted bill for Undo functionality
    last_deleted_bill = None 
    
    def __init__(self, master, app_instance):
        super().__init__(master)
        self.app = app_instance
        self.grid_columnconfigure(0, weight=1)
        self.grid_rowconfigure(1, weight=1)

        ctk.CTkLabel(self, text="Sales History (பில் வரலாறு)", font=ctk.CTkFont(size=18, weight="bold")).grid(row=0, column=0, padx=10, pady=(10, 5), sticky="w")
        
        # New Frame for Clear/Undo Buttons
        control_frame = ctk.CTkFrame(self)
        control_frame.grid(row=0, column=0, padx=10, pady=(10, 5), sticky="e")
        
        self.clear_all_button = ctk.CTkButton(control_frame, text="Clear All History", fg_color="darkred", hover_color="#8B0000", command=self.clear_all_history)
        self.clear_all_button.grid(row=0, column=0, padx=5)
        
        self.undo_button = ctk.CTkButton(control_frame, text="Undo Delete", state="disabled", command=self.undo_delete)
        self.undo_button.grid(row=0, column=1, padx=5)
        self.update_undo_button_state() # Initial state check
        
        # NEW: Weekly Billing Controls
        weekly_control_frame = ctk.CTkFrame(self)
        weekly_control_frame.grid(row=0, column=0, padx=10, pady=(10, 5), sticky="nsw")
        
        ctk.CTkLabel(weekly_control_frame, text="Weekly Bill Options:", font=ctk.CTkFont(weight="bold")).grid(row=0, column=0, columnspan=2, padx=5, pady=5, sticky="w")
        
        # Customer Dropdown for Weekly Filter
        self.weekly_customer_options = get_customers()
        self.weekly_customer_var = ctk.StringVar(value="Select Customer")
        self.weekly_customer_dropdown = ctk.CTkOptionMenu(weekly_control_frame, variable=self.weekly_customer_var, values=self.weekly_customer_options, width=150)
        self.weekly_customer_dropdown.grid(row=1, column=0, padx=5, pady=5, sticky="w")
        
        # Generate Weekly Bill Button
        self.generate_weekly_button = ctk.CTkButton(weekly_control_frame, text="Generate Weekly Bill", command=self.generate_weekly_bill)
        self.generate_weekly_button.grid(row=1, column=1, padx=5, pady=5)
        
        # Need to update customer list in dropdown when history is loaded/refreshed
        self.load_weekly_customer_options()
        

        
        self.history_list_frame = ctk.CTkScrollableFrame(self)
        self.history_list_frame.grid(row=1, column=0, padx=10, pady=5, sticky="nsew") 
        self.history_list_frame.grid_columnconfigure(0, weight=1)
        
    def load_weekly_customer_options(self):
        customers = get_customers()
        if customers:
            self.weekly_customer_options = customers
            self.weekly_customer_dropdown.configure(values=self.weekly_customer_options)
            if self.weekly_customer_var.get() not in customers:
                self.weekly_customer_var.set("Select Customer")

    def generate_weekly_bill(self):
        """Consolidates bills for a selected customer and generates a single PDF."""
        customer = self.weekly_customer_var.get()
        if customer == "Select Customer" or not customer:
            messagebox.showerror("Error", "Please select a customer for weekly billing.")
            return

        if not messagebox.askyesno("Confirm Weekly Bill", f"Generate consolidated bill for ALL recorded sales of customer: {customer}?"):
            return

        conn = sqlite3.connect(DB_NAME)
        cursor = conn.cursor()

        # Fetch all bills for the customer
        cursor.execute("SELECT bill_id, transaction_date, total_amount, items_json FROM sales_history WHERE customer_name = ? ORDER BY transaction_date ASC", (customer,))
        sales = cursor.fetchall()
        conn.close()

        if not sales:
            messagebox.showinfo("Info", f"No saved bills found for customer: {customer}.")
            return

        # 1. Consolidate items
        consolidated_items_dict = {}
        total_grand_amount = 0.0
        first_date = datetime.strptime(sales[0][1], '%Y-%m-%d %H:%M:%S').strftime('%d-%b-%Y')
        last_date = datetime.strptime(sales[-1][1], '%Y-%m-%d %H:%M:%S').strftime('%d-%b-%Y')
        
        for bill_id, date, total_amount, items_json in sales:
            items = json.loads(items_json)
            total_grand_amount += total_amount
            
            for name, quantity, rate, total in items:
                # Key based on item name and rate to group items sold at the same price
                key = (name, rate)
                if key not in consolidated_items_dict:
                    consolidated_items_dict[key] = {
                        'name': name,
                        'quantity': 0.0,
                        'rate': rate,
                        'total': 0.0,
                        'dates': []
                    }
                
                consolidated_items_dict[key]['quantity'] += quantity
                consolidated_items_dict[key]['total'] += total
                consolidated_items_dict[key]['dates'].append(datetime.strptime(date, '%Y-%m-%d %H:%M:%S').strftime('%d %b'))

        consolidated_items = list(consolidated_items_dict.values())
        
        # 2. Generate PDF (using bill_id=0 as flag for consolidated bill)
        date_range_str = f"{first_date} to {last_date}"
        generate_pdf_invoice(
            bill_id=0,
            customer_name=customer,
            items=consolidated_items,
            total_amount=total_grand_amount,
            title="WEEKLY CONSOLIDATED INVOICE",
            date_range=date_range_str,
        )
        
        # 3. Optional: Delete the merged individual bills after successful consolidation/printing
        if messagebox.askyesno("Consolidation Complete", f"Consolidated bill generated for {customer}.\nTotal: ₹{total_grand_amount:,.2f}.\n\nDo you want to PERMANENTLY delete the {len(sales)} individual daily bills for this period?"):
            conn = sqlite3.connect(DB_NAME)
            cursor = conn.cursor()
            
            # Delete selected bills
            bill_ids_to_delete = [str(s[0]) for s in sales]
            cursor.execute(f"DELETE FROM sales_history WHERE bill_id IN ({','.join(['?'] * len(bill_ids_to_delete))})", bill_ids_to_delete)
            conn.commit()
            conn.close()
            
            self.load_sales_history()  # Refresh list
            if self.app.dashboard_frame:
                self.app.dashboard_frame.load_report_data()
            
            messagebox.showinfo("Success", f"Consolidated Bill saved and {len(sales)} original bills deleted.")

    def load_sales_history(self):
        """Fetches and displays all sales history records."""
        self.load_weekly_customer_options() # Reload customers in case one was added/deleted
        for widget in self.history_list_frame.winfo_children():
            widget.destroy()

        conn = sqlite3.connect(DB_NAME)
        cursor = conn.cursor()
        cursor.execute("SELECT bill_id, transaction_date, customer_name, total_amount, items_json FROM sales_history ORDER BY bill_id DESC")
        sales = cursor.fetchall()
        conn.close()

        # Header Row
        header_frame = ctk.CTkFrame(self.history_list_frame, fg_color="transparent")
        # FIX: Changed column=1 and padding to align with the rest of the layout
        header_frame.grid(row=0, column=0, padx=5, pady=2, sticky="ew") 
        header_frame.grid_columnconfigure(0, weight=1) # Bill ID
        header_frame.grid_columnconfigure(1, weight=2) # Date & Time - more space
        header_frame.grid_columnconfigure(2, weight=3) # Customer - most space
        header_frame.grid_columnconfigure(3, weight=1) # Total
        header_frame.grid_columnconfigure(4, weight=0) # View button column
        header_frame.grid_columnconfigure(5, weight=0) # Print button column
        header_frame.grid_columnconfigure(6, weight=0) # Delete button column
        
        ctk.CTkLabel(header_frame, text="BILL ID", font=ctk.CTkFont(weight="bold")).grid(row=0, column=0, padx=5, sticky="w")
        ctk.CTkLabel(header_frame, text="DATE & TIME", font=ctk.CTkFont(weight="bold")).grid(row=0, column=1, padx=5, sticky="w")
        ctk.CTkLabel(header_frame, text="CUSTOMER", font=ctk.CTkFont(weight="bold")).grid(row=0, column=2, padx=5, sticky="w")
        ctk.CTkLabel(header_frame, text="TOTAL (₹)", font=ctk.CTkFont(weight="bold")).grid(row=0, column=3, padx=5, sticky="w")
        
        for i, sale in enumerate(sales):
            bill_id, date, customer, total, items_json = sale
            
            row_frame = ctk.CTkFrame(self.history_list_frame, fg_color=("gray80", "gray25"))
            row_frame.grid(row=i + 1, column=0, padx=5, pady=5, sticky="ew")
            
            # FIX: Match the column configuration with the header for alignment
            row_frame.grid_columnconfigure(0, weight=1)
            row_frame.grid_columnconfigure(1, weight=2)
            row_frame.grid_columnconfigure(2, weight=3)
            row_frame.grid_columnconfigure(3, weight=1)
            row_frame.grid_columnconfigure(4, weight=0) # View button column
            row_frame.grid_columnconfigure(5, weight=0) # Print button column
            row_frame.grid_columnconfigure(6, weight=0) # Delete button column


            ctk.CTkLabel(row_frame, text=str(bill_id)).grid(row=0, column=0, padx=5, sticky="w")
            ctk.CTkLabel(row_frame, text=date).grid(row=0, column=1, padx=5, sticky="w")
            ctk.CTkLabel(row_frame, text=customer).grid(row=0, column=2, padx=5, sticky="w")
            ctk.CTkLabel(row_frame, text=f"₹{total:.2f}", font=ctk.CTkFont(weight="bold")).grid(row=0, column=3, padx=5, sticky="w")
            
            # View Details Button
            view_btn = ctk.CTkButton(row_frame, text="View Details", width=80, command=lambda b=bill_id, d=date, c=customer, i_json=items_json, t=total: self.view_bill_details(b, d, c, i_json, t))
            view_btn.grid(row=0, column=4, padx=5, sticky="e")
            
            # Print Again Button
            print_btn = ctk.CTkButton(row_frame, text="Print Again", width=80, command=lambda b=bill_id, c=customer, i_json=items_json, t=total: self.regenerate_pdf(b, c, i_json, t))
            print_btn.grid(row=0, column=5, padx=5, sticky="e")
            
            # NEW: Delete Individual Button
            delete_btn = ctk.CTkButton(row_frame, text="Delete", width=60, fg_color="red", hover_color="#8B0000", command=lambda s=sale: self.delete_individual_bill(s))
            delete_btn.grid(row=0, column=6, padx=5, sticky="e")
            
    def update_undo_button_state(self):
        """Checks if there's a deleted bill to enable/disable the Undo button."""
        if HistoryScreen.last_deleted_bill:
            self.undo_button.configure(state="normal")
        else:
            self.undo_button.configure(state="disabled")
            
    def delete_individual_bill(self, sale_data):
        """Deletes a specific bill and prepares data for undo."""
        bill_id, date, customer, total, items_json = sale_data
        
        if messagebox.askyesno("Confirm Delete", f"Are you sure you want to delete Bill ID {bill_id}?\nTotal: ₹{total:.2f}"):
            conn = sqlite3.connect(DB_NAME)
            cursor = conn.cursor()
            try:
                cursor.execute("DELETE FROM sales_history WHERE bill_id = ?", (bill_id,))
                conn.commit()
                conn.close()
                
                # Store the deleted bill for potential undo
                HistoryScreen.last_deleted_bill = sale_data
                messagebox.showinfo("Deleted", f"Bill ID {bill_id} deleted. Click 'Undo Delete' to restore it.")
                
                self.load_sales_history()
                self.update_undo_button_state()
                if self.app.dashboard_frame:
                    self.app.dashboard_frame.load_report_data()

            except sqlite3.Error as e:
                messagebox.showerror("Database Error", f"Failed to delete bill: {e}")
                conn.close()

    def undo_delete(self):
        """Restores the last deleted bill."""
        if HistoryScreen.last_deleted_bill:
            bill_id, date, customer, total, items_json = HistoryScreen.last_deleted_bill
            
            conn = sqlite3.connect(DB_NAME)
            cursor = conn.cursor()
            try:
                # Re-insert the deleted record (using the original ID is tricky due to AUTOINCREMENT, 
                # so we insert it as a new record and let SQLite handle the ID, or use REPLACE)
                # We will use REPLACE to try and preserve the ID if possible, otherwise it will create new ID.
                cursor.execute('''
                    INSERT OR REPLACE INTO sales_history (bill_id, transaction_date, customer_name, total_amount, items_json)
                    VALUES (?, ?, ?, ?, ?)
                ''', (bill_id, date, customer, total, items_json))
                conn.commit()
                conn.close()
                
                messagebox.showinfo("Restored", f"Bill ID {bill_id} restored.")
                HistoryScreen.last_deleted_bill = None # Clear undo buffer
                
                self.load_sales_history()
                self.update_undo_button_state()
                if self.app.dashboard_frame:
                    self.app.dashboard_frame.load_report_data()
                
            except sqlite3.Error as e:
                messagebox.showerror("Database Error", f"Failed to restore bill: {e}")
                conn.close()
        else:
            messagebox.showinfo("Info", "No recent bill to undo.")

    def clear_all_history(self):
        """Deletes all records from sales history after confirmation."""
        if messagebox.askyesno("Confirm Clear ALL", "WARNING: This will permanently delete ALL sales history records. Are you ABSOLUTELY sure?"):
            conn = sqlite3.connect(DB_NAME)
            cursor = conn.cursor()
            try:
                # Note: We don't save all history for undo due to large size, but clear the last undo record
                HistoryScreen.last_deleted_bill = None
                cursor.execute("DELETE FROM sales_history")
                conn.commit()
                conn.close()
                messagebox.showinfo("Cleared", "All sales history records have been permanently deleted.")
                
                self.load_sales_history()
                self.update_undo_button_state()
                if self.app.dashboard_frame:
                    self.app.dashboard_frame.load_report_data()
                    
            except sqlite3.Error as e:
                messagebox.showerror("Database Error", f"Failed to clear history: {e}")
                conn.close()
            
    def regenerate_pdf(self, bill_id, customer, items_json, total_amount):
        """Regenerates the PDF for a selected historical bill."""
        try:
            items = json.loads(items_json)
            pdf_path = generate_pdf_invoice(bill_id, customer, items, total_amount)
            messagebox.showinfo("PDF Generated", f"Bill (ID: {bill_id}) PDF re-generated at:\n{pdf_path}\nReady for printing.")
        except Exception as e:
            messagebox.showerror("Error", f"Failed to regenerate PDF: {e}")

    def view_bill_details(self, bill_id, date, customer, items_json, total_amount):
        """Displays the full details of a selected bill in a new modal window."""
        items = json.loads(items_json)

        # Create a Toplevel window for the modal view
        view_window = ctk.CTkToplevel(self.app)
        view_window.title(f"Bill Details - ID: {bill_id}")
        view_window.geometry("600x450")
        view_window.attributes("-topmost", True) # Keep window on top
        view_window.grid_columnconfigure(0, weight=1)
        view_window.grid_rowconfigure(2, weight=1)
        
        # Data for passing to load_bill_for_edit
        bill_data_for_edit = (bill_id, customer, items_json, total_amount)

        # Header Info
        header_label = ctk.CTkLabel(view_window, text=f"Bill ID: {bill_id} | Date: {date}", font=ctk.CTkFont(size=16, weight="bold"))
        header_label.grid(row=0, column=0, padx=20, pady=10, sticky="w")
        ctk.CTkLabel(view_window, text=f"Customer: {customer}", font=ctk.CTkFont(size=14)).grid(row=1, column=0, padx=20, pady=(0, 10), sticky="w")
        
        # Itemized List Frame
        list_frame = ctk.CTkScrollableFrame(view_window, label_text="Itemized Breakdown")
        list_frame.grid(row=2, column=0, padx=20, pady=10, sticky="nsew")
        list_frame.grid_columnconfigure(0, weight=4)
        list_frame.grid_columnconfigure(1, weight=2)
        list_frame.grid_columnconfigure(2, weight=1)
        list_frame.grid_columnconfigure(3, weight=1)

        # Item List Header
        ctk.CTkLabel(list_frame, text="PRODUCT", font=ctk.CTkFont(weight="bold")).grid(row=0, column=0, padx=5, pady=5, sticky="w")
        ctk.CTkLabel(list_frame, text="QUANTITY", font=ctk.CTkFont(weight="bold")).grid(row=0, column=1, padx=5, pady=5, sticky="w")
        ctk.CTkLabel(list_frame, text="RATE", font=ctk.CTkFont(weight="bold")).grid(row=0, column=2, padx=5, pady=5, sticky="w")
        ctk.CTkLabel(list_frame, text="TOTAL", font=ctk.CTkFont(weight="bold")).grid(row=0, column=3, padx=5, pady=5, sticky="w")

        # Populate Items
        for i, item in enumerate(items):
            name, quantity, rate, total = item
            ctk.CTkLabel(list_frame, text=name).grid(row=i+1, column=0, padx=5, pady=2, sticky="w")
            ctk.CTkLabel(list_frame, text=format_quantity(quantity)).grid(row=i+1, column=1, padx=5, pady=2, sticky="w")
            ctk.CTkLabel(list_frame, text=f"@{rate:.2f}").grid(row=i+1, column=2, padx=5, pady=2, sticky="w")
            ctk.CTkLabel(list_frame, text=f"₹{total:.2f}", font=ctk.CTkFont(weight="bold")).grid(row=i+1, column=3, padx=5, pady=2, sticky="w")

        # Footer Total
        footer_frame = ctk.CTkFrame(view_window)
        footer_frame.grid(row=3, column=0, padx=20, pady=10, sticky="ew")
        footer_frame.grid_columnconfigure(0, weight=1)
        footer_frame.grid_columnconfigure(1, weight=1)
        
        ctk.CTkLabel(footer_frame, text=f"GRAND TOTAL: ₹{total_amount:.2f}", font=ctk.CTkFont(size=16, weight="bold"), text_color="lightgreen").grid(row=0, column=0, padx=20, pady=10, sticky="e")
        
        # New Edit Button in Modal
        def _on_edit_bill():
            view_window.destroy()
            self.app.billing_frame.load_bill_for_edit(bill_data_for_edit)

        edit_button = ctk.CTkButton(footer_frame, text="Edit Bill", command=_on_edit_bill)
        edit_button.grid(row=0, column=1, padx=20, pady=10, sticky="w")
        
        view_window.grab_set() # Make the modal window exclusive


# --- APPLICATION START ---
if __name__ == "__main__":
    # BASE_PATH is defined at module import to support frozen apps (PyInstaller).
    setup_database_and_folders()
    app = App()
    app.mainloop()
