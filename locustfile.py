# D:\restarent_application66\locustfile.py

from locust import HttpUser, task, between


class OfferZoneUser(HttpUser):
    wait_time = between(1, 3)

    @task
    def user_login_page(self):
        self.client.get("/user/login/")