from django.urls import path
from . import views

urlpatterns = [
    path("", views.news_list, name="news_list"),
    path("create/", views.news_create, name="news_create"),
    path("<slug:slug>/", views.news_detail, name="news_detail"),
    path("<slug:slug>/edit/", views.news_edit, name="news_edit"),
    path("<slug:slug>/delete/", views.news_delete, name="news_delete"),
    path("<slug:slug>/toggle-archive/", views.news_toggle_archive, name="news_toggle_archive"),
    path("<slug:slug>/set-breaking/", views.news_set_breaking, name="news_set_breaking"),
]

