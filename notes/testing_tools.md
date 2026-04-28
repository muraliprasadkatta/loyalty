python -m pip install locust (for load test)

terminal 1
python manage.py runserver 127.0.0.1:8000 --noreload

terminal 2
python -m pip install waitress
waitress-serve --listen=127.0.0.1:8000 offerzone.wsgi:application