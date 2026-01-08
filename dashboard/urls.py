# dashboard/urls.py
from django.urls import path
from .views import DashboardOverviewView, AdminDashboardTotalsView

app_name = "dashboard"

urlpatterns = [
    path("overview/", DashboardOverviewView.as_view(), name="overview"),
    path("admin/totals/", AdminDashboardTotalsView.as_view(), name="admin-dashboard-totals"),

]
