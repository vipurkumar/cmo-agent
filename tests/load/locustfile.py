"""Load testing with Locust for CMO Agent.

Run with:
    pip install locust
    locust -f tests/load/locustfile.py --host http://localhost:8000

Or headless:
    locust -f tests/load/locustfile.py --host http://localhost:8000 \
        --headless -u 100 -r 10 --run-time 5m
"""

from locust import HttpUser, between, task, events


class CMOAgentUser(HttpUser):
    """Simulates a customer using the CMO Agent API."""

    wait_time = between(0.5, 2)

    def on_start(self):
        """Set up auth headers. In real load tests, create a workspace first."""
        self.api_key = "cmo_load_test_key"  # Set a real key for actual load testing
        self.headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
        }

    @task(10)
    def health_check(self):
        """Most frequent -- lightweight health check."""
        self.client.get("/health")

    @task(5)
    def list_campaigns(self):
        """List campaigns with pagination."""
        self.client.get(
            "/campaigns?page=1&page_size=10",
            headers=self.headers,
            name="/campaigns",
        )

    @task(3)
    def get_automation_status(self):
        """Check automation status."""
        self.client.get(
            "/api/v1/automation/status",
            headers=self.headers,
            name="/api/v1/automation/status",
        )

    @task(2)
    def get_usage(self):
        """Check usage stats."""
        self.client.get(
            "/api/v1/usage?days=7",
            headers=self.headers,
            name="/api/v1/usage",
        )

    @task(2)
    def list_notifications(self):
        """Check notifications."""
        self.client.get(
            "/api/v1/notifications?limit=10",
            headers=self.headers,
            name="/api/v1/notifications",
        )

    @task(1)
    def get_audit_summary(self):
        """Check audit summary."""
        self.client.get(
            "/api/v1/audit/summary",
            headers=self.headers,
            name="/api/v1/audit/summary",
        )

    @task(1)
    def create_campaign(self):
        """Create a campaign (write operation)."""
        self.client.post(
            "/campaigns",
            json={
                "name": "Load Test Campaign",
                "icp_criteria": {"industries": ["SaaS"]},
            },
            headers=self.headers,
            name="/campaigns [POST]",
        )

    @task(1)
    def search_kb(self):
        """Search knowledge base."""
        self.client.get(
            "/api/v1/kb/search?query=pricing+objection&limit=3",
            headers=self.headers,
            name="/api/v1/kb/search",
        )

    @task(1)
    def export_scores(self):
        """Export scores as JSON."""
        self.client.get(
            "/api/v1/export/scores?format=json&limit=10",
            headers=self.headers,
            name="/api/v1/export/scores",
        )


class AdminUser(HttpUser):
    """Simulates an admin user -- lower frequency, heavier operations."""

    wait_time = between(5, 15)
    weight = 1  # 1 admin per 10 regular users

    def on_start(self):
        self.admin_key = "admin_load_test_key"
        self.headers = {
            "Authorization": f"Bearer {self.admin_key}",
            "Content-Type": "application/json",
        }

    @task(1)
    def admin_stats(self):
        """Check admin dashboard stats."""
        self.client.get(
            "/admin/stats",
            headers=self.headers,
            name="/admin/stats",
        )
