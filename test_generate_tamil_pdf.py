from svs_billing_app import generate_pdf_invoice

# Minimal test data with Tamil product and customer names
items = [
    ("தக்காளி (Tomato)", 1.5, 25.0, 37.5),
    ("வெங்காயம் (Onion)", 2.0, 35.0, 70.0)
]

filename = generate_pdf_invoice(22, "தர்மராஜா", items, total_amount=107.5, title="TEST INVOICE - TAMIL")
print("Generated:", filename)
    
    