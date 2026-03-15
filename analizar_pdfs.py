import pdfplumber
from pathlib import Path

pdf_dir = Path(r"C:\Users\david\OneDrive\Escritorio\proyecto terminal\pdf_pruebas")
pdfs = list(pdf_dir.glob("*.pdf"))

for pdf_path in pdfs:
    print(f"\n{'='*80}")
    print(f"ARCHIVO: {pdf_path.name}")
    print(f"{'='*80}")
    
    try:
        with pdfplumber.open(pdf_path) as pdf:
            print(f"Total de páginas: {len(pdf.pages)}\n")
            
            for page_num, page in enumerate(pdf.pages[:3], 1):  # Primeras 3 páginas
                print(f"\n--- PÁGINA {page_num} ---")
                texto = page.extract_text()
                if texto:
                    # Mostrar primeras 1500 caracteres
                    print(texto[:1500])
                    print("\n[...]" if len(texto) > 1500 else "")
                else:
                    print("(sin texto extraído)")
                    
    except Exception as e:
        print(f"Error: {e}")
