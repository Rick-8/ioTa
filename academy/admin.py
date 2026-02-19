from django.contrib import admin
from .models import (
    Course,
    Module,
    Lesson,
    Question,
    Choice,
    ModuleProgress,
    LessonProgress,
    FinalTestSubmission,
    ManagerDocument,
    CourseAssignment,
)

# =============================
# INLINE CONFIG
# =============================

class LessonInline(admin.TabularInline):
    model = Lesson
    extra = 1
    fields = ("title", "order")
    ordering = ("order",)


class ChoiceInline(admin.TabularInline):
    model = Choice
    extra = 2
    fields = ("text", "is_correct")
    ordering = ("id",)


# =============================
# COURSE ADMIN
# =============================

@admin.register(Course)
class CourseAdmin(admin.ModelAdmin):
    list_display = ("title", "order", "is_active")
    list_editable = ("order", "is_active")
    search_fields = ("title", "description")
    ordering = ("order",)


# =============================
# MODULE ADMIN
# =============================

@admin.register(Module)
class ModuleAdmin(admin.ModelAdmin):
    list_display = ("title", "course", "order", "min_score_to_pass", "is_mandatory")
    list_editable = ("order", "min_score_to_pass", "is_mandatory")
    list_filter = ("course", "is_mandatory")
    search_fields = ("title", "description")
    ordering = ("course__order", "order")
    inlines = [LessonInline]


# =============================
# LESSON ADMIN
# =============================

@admin.register(Lesson)
class LessonAdmin(admin.ModelAdmin):
    list_display = ("title", "module", "order")
    list_editable = ("order",)
    list_filter = ("module",)
    search_fields = ("title", "content")
    ordering = ("module__order", "order")


# =============================
# QUESTION ADMIN
# =============================

@admin.register(Question)
class QuestionAdmin(admin.ModelAdmin):
    list_display = ("text_short", "module", "order")
    list_editable = ("order",)
    list_filter = ("module",)
    search_fields = ("text",)
    ordering = ("module__order", "order")
    inlines = [ChoiceInline]

    def text_short(self, obj):
        return obj.text[:60] + "..." if len(obj.text) > 60 else obj.text
    text_short.short_description = "Question"


# =============================
# CHOICE ADMIN (RARELY NEEDED DIRECTLY)
# =============================

@admin.register(Choice)
class ChoiceAdmin(admin.ModelAdmin):
    list_display = ("text", "question", "is_correct")
    list_filter = ("is_correct", "question__module")
    search_fields = ("text",)
    ordering = ("question__id",)


# =============================
# MODULE PROGRESS ADMIN
# =============================

@admin.register(ModuleProgress)
class ModuleProgressAdmin(admin.ModelAdmin):
    list_display = ("user", "module", "status", "score", "completed_at")
    list_filter = ("status", "module__course", "module")
    search_fields = ("user__username", "user__email", "module__title")
    ordering = ("user__username", "module__order")


# =============================
# LESSON PROGRESS ADMIN
# =============================

@admin.register(LessonProgress)
class LessonProgressAdmin(admin.ModelAdmin):
    list_display = ("user", "lesson", "completed", "completed_at")
    list_filter = ("completed", "lesson__module")
    search_fields = ("user__username", "lesson__title")
    ordering = ("lesson__module__order", "lesson__order")


# =============================
# FINAL TEST SUBMISSION ADMIN
# =============================

@admin.register(FinalTestSubmission)
class FinalTestSubmissionAdmin(admin.ModelAdmin):
    list_display = ("user", "module", "submitted_at", "reviewed", "is_passed")
    list_filter = ("reviewed", "is_passed", "module__course")
    search_fields = ("user__username", "module__title")
    ordering = ("-submitted_at",)


# =============================
# MANAGER UPLOADED DOCUMENTS
# =============================

@admin.register(ManagerDocument)
class ManagerDocumentAdmin(admin.ModelAdmin):
    list_display = ("file", "uploaded_by", "uploaded_at")
    search_fields = ("file", "uploaded_by__username")
    ordering = ("-uploaded_at",)


# =============================
# COURSE ASSIGNMENTS
# =============================

@admin.register(CourseAssignment)
class CourseAssignmentAdmin(admin.ModelAdmin):
    list_display = ("user", "group", "course", "assigned_at")
    list_filter = ("course", "group")
    search_fields = ("user__username", "group__name", "course__title")
    ordering = ("-assigned_at",)
