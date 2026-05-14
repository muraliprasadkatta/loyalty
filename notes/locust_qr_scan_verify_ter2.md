$env:DB_NAME="offerzone_loadtest_db"
$env:DB_USER="postgres"
$env:DB_PASSWORD="Katta@123"

python -m locust -f locust_qr_scan_verify.py --host=http://127.0.0.1:8000



count check:
----------

python manage.py shell -c "from offers.models import UserVisitEvent, QRToken; from django.contrib.auth import get_user_model; User=get_user_model(); print('Users:', User.objects.filter(username__startswith='qrload').count()); print('QR tokens:', QRToken.objects.count()); print('Visits:', UserVisitEvent.objects.count())"


db clean:
--------

python manage.py shell -c "from offers.models import QRToken; print('Deleting QR tokens:', QRToken.objects.count()); QRToken.objects.all().delete(); print('Done')"

user vsit clean:
----------------python manage.py shell -c "from offers.models import UserVisitEvent; print('Deleting visits:', UserVisitEvent.objects.count()); UserVisitEvent.objects.all().delete(); print('Done')"

python manage.py shell -c "from offers.models import UserVisitEvent; print('Deleting visits:', UserVisitEvent.objects.count()); UserVisitEvent.objects.all().delete(); print('Done')"