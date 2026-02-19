# academy/urls.py

from django.urls import path
from . import views

urlpatterns = [

    # ============================
    # STUDENT AREA
    # ============================
    path("", views.dashboard, name="academy_dashboard"),

    path(
        "course/<slug:course_slug>/",
        views.course_detail,
        name="academy_course_detail",
    ),

    path(
        "course/<slug:course_slug>/module/<slug:module_slug>/",
        views.module_detail,
        name="academy_module_detail",
    ),

    path(
        "course/<slug:course_slug>/module/<slug:module_slug>/lesson/<int:lesson_id>/",
        views.lesson_detail,
        name="academy_lesson_detail",
    ),

    path(
        "lesson/<int:lesson_id>/complete/",
        views.academy_complete_lesson,
        name="academy_complete_lesson",
    ),

    path(
        "course/<slug:course_slug>/module/<slug:module_slug>/quiz/",
        views.module_quiz,
        name="academy_module_quiz",
    ),

    path(
        "course/<slug:course_slug>/module/<slug:module_slug>/final-test/",
        views.final_test,
        name="academy_final_test",
    ),

    path(
        "certificate/<int:certificate_id>/",
        views.certificate_detail,
        name="academy_certificate_detail",
    ),

    # ============================
    # MANAGER DASHBOARD + TOOLS
    # ============================
    path("managers/", views.manager_dashboard, name="academy_manager_dashboard"),

    path(
        "managers/tools/",
        views.manager_tools,
        name="academy_manager_tools",
    ),

    path(
        "managers/documents/",
        views.manager_documents,
        name="academy_manager_documents",
    ),

    path(
        "managers/users/",
        views.manager_users,
        name="academy_manager_users",
    ),

    # Certificates
    path(
        "managers/certificates/",
        views.manager_certificates,
        name="academy_manager_certificates",
    ),
    path(
        "managers/certificate/<int:certificate_id>/pdf/",
        views.generate_certificate_pdf,
        name="academy_generate_certificate_pdf",
    ),

    # Final Test Submissions
    path(
        "managers/final-tests/",
        views.manager_final_tests,
        name="academy_manager_final_tests",
    ),
    path(
        "managers/final-tests/pass/<int:submission_id>/",
        views.manager_mark_pass,
        name="academy_manager_mark_pass",
    ),

    # ============================
    # QUESTION BUILDER
    # ============================
    path(
        "questions/add/",
        views.add_question,
        name="academy_add_question",
    ),

    # ============================
    # COURSE MANAGEMENT
    # ============================
    path(
        "managers/course/add/",
        views.create_course,
        name="academy_add_course",
    ),

    path(
        "managers/courses/",
        views.manage_courses,
        name="academy_manage_courses",
    ),

    path(
        "managers/course/<int:course_id>/delete/",
        views.delete_course,
        name="academy_delete_course",
    ),

    # ============================
    # MODULE MANAGEMENT
    # ============================
    path(
        "managers/course/<int:course_id>/modules/",
        views.manage_modules,
        name="academy_manage_modules",
    ),

    path(
        "managers/course/<int:course_id>/modules/add/",
        views.add_module,
        name="academy_add_module",
    ),

    path(
        "managers/module/<int:module_id>/delete/",
        views.delete_module,
        name="academy_delete_module",
    ),

    # ============================
    # LESSON MANAGEMENT
    # ============================
    path(
        "managers/module/<int:module_id>/lessons/",
        views.manage_lessons,
        name="academy_manage_lessons",
    ),

    path(
        "managers/module/<int:module_id>/lessons/add/",
        views.add_lesson,
        name="academy_add_lesson",
    ),

    path(
        "managers/lesson/<int:lesson_id>/content/",
        views.edit_lesson_content,
        name="academy_edit_lesson_content",
    ),

    path(
        "managers/lesson/<int:lesson_id>/delete/",
        views.delete_lesson,
        name="academy_delete_lesson",
    ),
    path(
        "managers/driver-progress/",
        views.manager_driver_progress,
        name="academy_manager_driver_progress",
    ),
    # QUESTION MANAGEMENT
    path("manager/questions/<int:question_id>/edit/", views.edit_question, name="academy_edit_question"),

    path("manager/choices/<int:choice_id>/update/", views.update_choice, name="academy_update_choice"),
    path("manager/choices/<int:choice_id>/delete/", views.delete_choice, name="academy_delete_choice"),

    path("manager/questions/<int:question_id>/choices/add/", views.add_choice, name="academy_add_choice"),
    path("managers/questions/", views.manage_questions, name="academy_manage_questions"),
    path("managers/questions/import/", views.import_questions, name="academy_import_questions"),
    path(
        "managers/assign/",
        views.manager_assign,
        name="academy_manager_assign",
    ),



]
