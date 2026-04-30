All Claims mobile issue reason:
branch_all_claims.html direct ga render avuthundhi, kani complete HTML structure/head ledu.
Viewport meta tag missing kabatti mobile browser page ni desktop width laga treat chesindi.
Anduke @media (max-width: 767px) mobile CSS fire avvakunda table window view lane shrink ayindi.
Fix: branch_all_claims.html top lo <!DOCTYPE html>, <html>, <head>, viewport meta add chesam.
Bottom lo </body></html> add chesi, unused {% block content %}/{% endblock %} remove chesam.