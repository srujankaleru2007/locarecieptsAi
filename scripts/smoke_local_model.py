"""Optional local model smoke test using a generated fictional receipt only."""
import argparse
import sys
from pathlib import Path
from io import BytesIO
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from PIL import Image, ImageDraw, ImageFont
from localreceipts.documents import prepare_document
from localreceipts.extraction import extract_receipt_data

parser = argparse.ArgumentParser()
parser.add_argument('--model', default='llama3.2-vision')
args = parser.parse_args()
image = Image.new('RGB', (1100, 650), 'white')
draw = ImageDraw.Draw(image)
font = ImageFont.load_default(size=34)
for i, line in enumerate([
    'SAMPLE SOFTWARE STORE', 'TAX INVOICE - FICTIONAL TEST DATA',
    'Invoice date: 2026-10-19', 'Item: Software subscription',
    'Subtotal: INR 1000.00', 'GST tax: INR 180.00', 'TOTAL: INR 1180.00'
]):
    draw.text((40, 40 + i * 75), line, font=font, fill='black')
content = BytesIO()
image.save(content, 'PNG')
row, issues = extract_receipt_data(prepare_document('synthetic.png', content.getvalue()), args.model)
print(row)
print('Review notes:', issues)
if row['TotalAmount'] != 1180.0 or row['TaxAmount'] != 180.0:
    raise SystemExit('Model did not accurately read the synthetic totals; review or choose another local vision model.')
print('PASS: synthetic total and tax matched.')
