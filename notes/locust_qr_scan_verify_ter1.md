$env:DB_NAME="offerzone_loadtest_db"
$env:DB_USER="postgres"
$env:DB_PASSWORD="Katta@123"




python manage.py shell -c "from django.conf import settings; print(settings.DATABASES['default']['ENGINE']); print(settings.DATABASES['default']['NAME'])"


output:
-----
django.db.backends.postgresql
offerzone_loadtest_db   

waitress-serve --listen=127.0.0.1:8000 offerzone.wsgi:application