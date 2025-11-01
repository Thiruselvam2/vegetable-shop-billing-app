    # Tests for SVS Billing App
from svs_billing_app import make_pdf_filename

def test_pdf_filename_sanitization():
    # Test basic customer name
    assert "Invoices/John Doe - " in make_pdf_filename("John Doe")
    
    # Test with special characters
    assert "Invoices/John-Doe - " in make_pdf_filename("John/Doe")
    
    # Test with Tamil characters
    assert "Invoices/முருகன் - " in make_pdf_filename("முருகன்")
    
    # Test with empty name
    assert "Invoices/Invoice - " in make_pdf_filename("")
    
    # Test with None
    assert "Invoices/Invoice - " in make_pdf_filename(None)
    
    # Test with very long name
    long_name = "A" * 100
    result = make_pdf_filename(long_name)
    assert len(result.split(" - ")[0]) <= 88  # 80 + len("Invoices/")
    
    # Test with special characters and spaces
    assert "Invoices/My-Store-Name - " in make_pdf_filename("My/Store\\Name")