$env:DB_NAME="offerzone_loadtest_db"
$env:DB_USER="postgres"
$env:DB_PASSWORD="Katta@123"
$env:QR_PRECREATE_COUNT="50"

python -m locust -f .\load_tests\locust_qr_scan_verify_precreated.py --host=http://127.0.0.1:8000 --web-port 8091

python -m locust -f .\load_tests\locust_qr_pin_verify_precreated.py --host=http://127.0.0.1:8000 --web-port 8092

count check:
----------

python manage.py shell -c "from offers.models import UserVisitEvent, QRToken; from django.contrib.auth import get_user_model; User=get_user_model(); print('Users:', User.objects.filter(username__startswith='qrload').count()); print('QR tokens:', QRToken.objects.count()); print('Visits:', UserVisitEvent.objects.count())"


db clean:
--------

python manage.py shell -c "from offers.models import QRToken; print('Deleting QR tokens:', QRToken.objects.count()); QRToken.objects.all().delete(); print('Done')"

user vsit clean:
----------------python manage.py shell -c "from offers.models import UserVisitEvent; print('Deleting visits:', UserVisitEvent.objects.count()); UserVisitEvent.objects.all().delete(); print('Done')"

python manage.py shell -c "from offers.models import UserVisitEvent; print('Deleting visits:', UserVisitEvent.objects.count()); UserVisitEvent.objects.all().delete(); print('Done')"


whichdb check:
--------------

python manage.py shell -c "from django.conf import settings; print(settings.DATABASES['default']['NAME'])"