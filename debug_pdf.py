import pdfplumber
import re

pdf_path = r"C:\Users\david\OneDrive\Escritorio\proyecto terminal\pdf_pruebas\estudiante_cardexfgomez241.pdf"

with pdfplumber.open(pdf_path) as pdf:
    texto = ""
    for page in pdf.pages:
        texto += page.extract_text() + "\n"

print("=" * 80)
print("TEXTO COMPLETO DEL KARDEX")
print("=" * 80)
print(texto)

# Ahora analizar con regex
print("\n" + "=" * 80)
print("ANÁLISIS CON REGEX")
print("=" * 80)

patron = re.compile(
    r'^\*?([A-Z]{2,4}\d{4})\s+(.+?)\s+(\d{6})\s+OP\d+\s+(\S+?)(?:\s+(\d+))?(?:\s+.*)?$',
    re.MULTILINE
)

matches = list(patron.finditer(texto))
print(f"Total de matches: {len(matches)}\n")

for i, match in enumerate(matches, 1):
    print(f"{i}. {match.group(1)}: {match.group(3)} - Cal: {match.group(4)}, Créditos: {match.group(5)}")
