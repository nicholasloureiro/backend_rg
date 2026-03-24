"""
URLs da API para o app accounts
"""

from django.urls import path

from .api_views import (
    CitySearchAPIView,
    ClientDeleteAPIView,
    ClientListAPIView,
    ClientRegisterAPIView,
    ClientSearchAPIView,
    ClientUpdateCPFAPIView,
    EmployeeListAPIView,
    EmployeeRegisterAPIView,
    EmployeeToggleStatusAPIView,
    EmployeeUpdateAPIView,
    GetUserMeAPIView,
    LoginAPIView,
    LogoutAPIView,
    PasswordResetAPIView,
    RefreshTokenAPIView,
    RegisterAPIView,
    UserSelfUpdateAPIView,
)

urlpatterns = [
    # Autenticação
    path("auth/login/", LoginAPIView.as_view(), name="api_login"),
    path("auth/register/", RegisterAPIView.as_view(), name="api_register"),
    path("auth/refresh/", RefreshTokenAPIView.as_view(), name="api_refresh"),
    path("auth/logout/", LogoutAPIView.as_view(), name="api_logout"),
    path("auth/me/", GetUserMeAPIView.as_view(), name="api_user_me"),
    path(
        "auth/me/update/", UserSelfUpdateAPIView.as_view(), name="api_user_self_update"
    ),
    path(
        "auth/password-reset/",
        PasswordResetAPIView.as_view(),
        name="api_password_reset",
    ),
    # Cidades
    path("cities/search/", CitySearchAPIView.as_view(), name="api_city_search"),
    # Funcionários
    path(
        "employees/register/",
        EmployeeRegisterAPIView.as_view(),
        name="api_employee_register",
    ),
    path("employees/list/", EmployeeListAPIView.as_view(), name="api_employee_list"),
    path(
        "employees/toggle-status/",
        EmployeeToggleStatusAPIView.as_view(),
        name="api_employee_toggle_status",
    ),
    path(
        "employees/<int:person_id>/update/",
        EmployeeUpdateAPIView.as_view(),
        name="api_employee_update",
    ),
    # Clientes
    path(
        "clients/register/", ClientRegisterAPIView.as_view(), name="api_client_register"
    ),
    path("clients/list/", ClientListAPIView.as_view(), name="api_client_list"),
    path("clients/search/", ClientSearchAPIView.as_view(), name="api_client_search"),
    path(
        "clients/<int:person_id>/delete/",
        ClientDeleteAPIView.as_view(),
        name="api_client_delete",
    ),
    path(
        "clients/<int:person_id>/update-cpf/",
        ClientUpdateCPFAPIView.as_view(),
        name="api_client_update_cpf",
    ),
]
