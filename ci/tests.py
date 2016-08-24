from django.test import TestCase, Client


class ViewTests(TestCase):

    def setUp(self):
        self.client = Client()

    def login(self):
        self.client.login(username='testuser', password='testpass')

    def test_redirect_to_login(self):
        response = self.client.get("/", follow=True)
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Please login to see this page")
