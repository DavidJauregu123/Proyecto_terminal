#!/usr/bin/env python3
import json

m = json.load(open('data/mapa_curricular_2021ID.json', encoding='utf-8'))
c0 = [x for x in m.values() if x.get('ciclo') == 0]
print(f'Ciclo 0 materias: {len(c0)}')

# Mostrar algunos ejemplos
for k, v in list(m.items())[:5]:
    if v.get('ciclo') == 0:
        print(f"  {k}: {v.get('nombre')} - Ciclo {v.get('ciclo')}")
