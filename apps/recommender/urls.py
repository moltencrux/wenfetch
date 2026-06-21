from django.shortcuts import redirect
from django.urls import path
from . import views

urlpatterns = [
    path("", lambda r: redirect("recommend"), name="home"),
    path("recommend/", views.recommend_view, name="recommend"),
    path("vocab/", views.vocab_list_index, name="vocab_list_index"),
    path("vocab/new/", views.vocab_list_create, name="vocab_list_create"),
    path("vocab/<int:pk>/", views.vocab_list_detail, name="vocab_list_detail"),
    path("vocab/<int:pk>/delete/", views.vocab_list_delete, name="vocab_list_delete"),
]
